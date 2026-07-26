"""Focused tests for frozen network-dataset analysis and persistence."""

from __future__ import annotations

import asyncio
import unittest
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
from fastapi import FastAPI
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.auth.service import get_current_user
from backend.app.database import models  # noqa: F401 - register old and new tables
from backend.app.database.network_models import (
    NetworkDataset,
    NetworkFlow,
    NetworkIncident,
    NetworkPrediction,
)
from backend.app.database.session import Base, get_db
from backend.app.network import analysis_service
from backend.app.network import service as network_service
from backend.app.network.routes import router
from backend.app.tests.test_network_ingestion import (
    asgi_request,
    dataset_bytes,
    feature_record,
)

TEST_MODEL_NAME = "Recall-oriented Random Forest"
TEST_MODEL_VERSION = "test-frozen-artifact-sha256"


def labelled_row(
    probability_percent: int,
    label: str,
    difficulty_level: int = 21,
) -> dict:
    """Create one valid labelled flow whose duration drives the fake score."""
    row = feature_record(probability_percent)
    row.update(
        {
            "label": label,
            "difficulty_level": difficulty_level,
            "num_failed_logins": probability_percent % 3,
            "logged_in": 1 if probability_percent % 2 else 0,
        }
    )
    return row


def fake_load_final_detector():
    """Return deterministic frozen-model metadata without loading the artifact."""
    return object(), {
        "selected_model_name": TEST_MODEL_NAME,
        "artifact_sha256": TEST_MODEL_VERSION,
        "selected_threshold": analysis_service.ATTACK_THRESHOLD,
    }


def fake_predict_network_flows(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Return deterministic probabilities without fitting or preprocessing."""
    probabilities = dataframe["duration"].astype(float).div(100).to_numpy()
    predicted_binary = (
        probabilities >= analysis_service.ATTACK_THRESHOLD
    ).astype("int8")
    result = dataframe.loc[:, ["protocol_type", "service", "flag"]].copy()
    result["rf_attack_probability"] = probabilities
    result["predicted_binary"] = predicted_binary
    result["predicted_class"] = [
        "attack" if value else "normal" for value in predicted_binary
    ]
    return result


def fake_summarize_predictions(predictions: pd.DataFrame) -> dict:
    """Confirm the bounded batch has prediction output without loading N3."""
    required = {
        "rf_attack_probability",
        "predicted_binary",
        "predicted_class",
    }
    if not required.issubset(predictions.columns):
        raise AssertionError("Fake prediction output is incomplete.")
    return {"prediction_data": {"total_records": len(predictions)}}


def forbidden_fit(*args, **kwargs):
    """Fail immediately if application analysis attempts any model fitting."""
    del args, kwargs
    raise AssertionError("Model fitting is forbidden during application inference.")


@contextmanager
def no_fitting_allowed():
    """Guard the main scikit-learn fitting entry points used by this project."""
    with ExitStack() as stack:
        for target, method_name in [
            (Pipeline, "fit"),
            (ColumnTransformer, "fit"),
            (ColumnTransformer, "fit_transform"),
            (OneHotEncoder, "fit"),
            (OneHotEncoder, "fit_transform"),
            (RandomForestClassifier, "fit"),
        ]:
            stack.enter_context(
                patch.object(target, method_name, new=forbidden_fit)
            )
        yield


class NetworkAnalysisApiTest(unittest.TestCase):
    """Verify authenticated, atomic, idempotent frozen-model analysis."""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        @event.listens_for(cls.engine, "connect")
        def enable_foreign_keys(dbapi_connection, connection_record):
            del connection_record
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        cls.Session = sessionmaker(bind=cls.engine)
        cls.app = FastAPI()
        cls.app.include_router(router)

        def override_db():
            session = cls.Session()
            try:
                yield session
            finally:
                session.close()

        cls.app.dependency_overrides[get_db] = override_db

    @classmethod
    def tearDownClass(cls):
        cls.app.dependency_overrides.clear()
        cls.engine.dispose()

    def setUp(self):
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.app.dependency_overrides.pop(get_current_user, None)

    def authenticate(self, role: str = "analyst") -> None:
        user = SimpleNamespace(id=1, username=f"{role}-user", role=role)
        self.app.dependency_overrides[get_current_user] = lambda: user

    def request(self, method: str, path: str) -> tuple[int, dict]:
        return asyncio.run(asgi_request(self.app, method, path))

    def seed_dataset(
        self,
        *,
        labelled: bool,
        rows: list[dict],
        filename: str = "network.txt",
    ) -> int:
        with self.Session() as session:
            response = network_service.ingest_network_dataset(
                session,
                filename,
                dataset_bytes(labelled, False, rows=rows),
            )
            return int(response["id"])

    def analysis_patches(self):
        """Patch only model loading/prediction while preserving service logic."""
        return (
            patch.object(
                analysis_service,
                "load_final_detector",
                side_effect=fake_load_final_detector,
            ),
            patch.object(
                analysis_service,
                "predict_network_flows",
                side_effect=fake_predict_network_flows,
            ),
            patch.object(
                analysis_service,
                "summarize_predictions",
                side_effect=fake_summarize_predictions,
            ),
        )

    def test_authentication_lookup_empty_and_processing_guards(self):
        labelled_id = self.seed_dataset(
            labelled=True,
            rows=[labelled_row(90, "back")],
        )
        status, _ = self.request(
            "POST", f"/network/datasets/{labelled_id}/analyze"
        )
        self.assertEqual(status, 401)

        self.authenticate("admin")
        unknown_status, _ = self.request(
            "POST", "/network/datasets/99999/analyze"
        )
        self.assertEqual(unknown_status, 404)

        with self.Session() as session:
            empty = NetworkDataset(
                filename="empty.csv",
                total_records=0,
                has_ground_truth=False,
                source_type="nsl_kdd_inference",
                analysis_status="uploaded",
            )
            session.add(empty)
            session.commit()
            empty_id = empty.id
        empty_status, empty_response = self.request(
            "POST", f"/network/datasets/{empty_id}/analyze"
        )
        self.assertEqual(empty_status, 400, empty_response)

        with self.Session() as session:
            dataset = session.get(NetworkDataset, labelled_id)
            dataset.analysis_status = "processing"
            session.commit()
        processing_status, processing_response = self.request(
            "POST", f"/network/datasets/{labelled_id}/analyze"
        )
        self.assertEqual(processing_status, 409, processing_response)

    def test_labelled_analysis_persists_predictions_incidents_and_metrics(self):
        self.authenticate()
        dataset_id = self.seed_dataset(
            labelled=True,
            rows=[
                labelled_row(20, "normal"),
                labelled_row(38, "normal"),
                labelled_row(60, "back"),
                labelled_row(75, "neptune"),
                labelled_row(90, "satan"),
            ],
            filename="labelled.csv",
        )
        load_patch, predict_patch, summary_patch = self.analysis_patches()
        with no_fitting_allowed(), load_patch, predict_patch, summary_patch:
            status, response = self.request(
                "POST", f"/network/datasets/{dataset_id}/analyze"
            )
        self.assertEqual(status, 200, response)
        self.assertEqual(response["analysis_status"], "completed")
        self.assertFalse(response["reused_existing"])
        self.assertEqual(response["total_flows"], 5)
        self.assertEqual(response["total_predictions"], 5)
        self.assertEqual(response["predicted_normal"], 1)
        self.assertEqual(response["predicted_attack"], 4)
        self.assertEqual(response["total_incidents"], 4)
        self.assertEqual(
            response["severity_counts"],
            {"critical": 1, "high": 1, "medium": 1, "low": 1},
        )
        self.assertEqual(response["model_name"], TEST_MODEL_NAME)
        self.assertEqual(response["model_version"], TEST_MODEL_VERSION)
        self.assertEqual(
            response["threshold"], analysis_service.ATTACK_THRESHOLD
        )

        benchmark = response["benchmark_metrics"]
        self.assertEqual(benchmark["actual_normal"], 2)
        self.assertEqual(benchmark["actual_attack"], 3)
        self.assertEqual(benchmark["true_negatives"], 1)
        self.assertEqual(benchmark["false_positives"], 1)
        self.assertEqual(benchmark["false_negatives"], 0)
        self.assertEqual(benchmark["true_positives"], 3)
        self.assertAlmostEqual(benchmark["accuracy"], 0.8)
        self.assertAlmostEqual(benchmark["precision"], 0.75)
        self.assertAlmostEqual(benchmark["recall"], 1.0)
        self.assertAlmostEqual(benchmark["f1"], 6 / 7)
        self.assertAlmostEqual(benchmark["f2"], 15 / 16)
        self.assertAlmostEqual(benchmark["false_positive_rate"], 0.5)
        self.assertAlmostEqual(benchmark["false_negative_rate"], 0.0)

        with self.Session() as session:
            dataset = session.get(NetworkDataset, dataset_id)
            predictions = (
                session.query(NetworkPrediction)
                .filter(NetworkPrediction.dataset_id == dataset_id)
                .order_by(NetworkPrediction.flow_id)
                .all()
            )
            incidents = (
                session.query(NetworkIncident)
                .filter(NetworkIncident.dataset_id == dataset_id)
                .order_by(NetworkIncident.risk_score)
                .all()
            )
            self.assertEqual(dataset.analysis_status, "completed")
            self.assertIsNotNone(dataset.analysis_started_at)
            self.assertIsNotNone(dataset.analysis_completed_at)
            self.assertIsNone(dataset.analysis_error)
            self.assertEqual(dataset.model_name, TEST_MODEL_NAME)
            self.assertEqual(dataset.model_threshold, 0.38)
            self.assertEqual(len(predictions), 5)
            self.assertEqual(
                [prediction.rf_attack_probability for prediction in predictions],
                [0.2, 0.38, 0.6, 0.75, 0.9],
            )
            self.assertEqual(
                [prediction.actual_binary for prediction in predictions],
                [0, 0, 1, 1, 1],
            )
            self.assertEqual(
                [prediction.is_correct for prediction in predictions],
                [True, False, True, True, True],
            )
            self.assertEqual(
                [incident.risk_score for incident in incidents],
                [38.0, 60.0, 75.0, 90.0],
            )
            self.assertEqual(
                [incident.severity for incident in incidents],
                ["low", "medium", "high", "critical"],
            )
            for incident in incidents:
                self.assertEqual(incident.status, "open")
                self.assertIn("protocol=", incident.evidence)
                self.assertIn("service=", incident.evidence)
                self.assertIn("flag=", incident.evidence)
                self.assertIn("not confirmation", incident.evidence)
                self.assertNotIn("source ip", incident.evidence.lower())
                self.assertNotIn("endpoint", incident.evidence.lower())
                self.assertNotIn("predicted family", incident.evidence.lower())
                self.assertNotIn("definitely malicious", incident.evidence.lower())
                self.assertIn("before blocking", incident.recommended_action)

    def test_inference_only_analysis_keeps_benchmark_fields_null(self):
        self.authenticate("admin")
        dataset_id = self.seed_dataset(
            labelled=False,
            rows=[feature_record(20), feature_record(90)],
        )
        load_patch, predict_patch, summary_patch = self.analysis_patches()
        with no_fitting_allowed(), load_patch, predict_patch, summary_patch:
            status, response = self.request(
                "POST", f"/network/datasets/{dataset_id}/analyze"
            )
        self.assertEqual(status, 200, response)
        self.assertIsNone(response["benchmark_metrics"])
        self.assertEqual(response["total_predictions"], 2)
        self.assertEqual(response["total_incidents"], 1)
        with self.Session() as session:
            predictions = session.query(NetworkPrediction).all()
            incidents = session.query(NetworkIncident).all()
            self.assertTrue(
                all(prediction.actual_binary is None for prediction in predictions)
            )
            self.assertTrue(
                all(prediction.is_correct is None for prediction in predictions)
            )
            self.assertTrue(
                all(incident.actual_label is None for incident in incidents)
            )
            self.assertTrue(
                all(incident.actual_family is None for incident in incidents)
            )

    def test_completed_analysis_is_reused_and_inconsistency_conflicts(self):
        self.authenticate()
        dataset_id = self.seed_dataset(
            labelled=True,
            rows=[labelled_row(20, "normal"), labelled_row(90, "back")],
        )
        load_patch, predict_patch, summary_patch = self.analysis_patches()
        with load_patch, predict_patch, summary_patch:
            first_status, first = self.request(
                "POST", f"/network/datasets/{dataset_id}/analyze"
            )
        self.assertEqual(first_status, 200, first)

        with (
            patch.object(
                analysis_service,
                "load_final_detector",
                side_effect=AssertionError("model must not reload"),
            ),
            patch.object(
                analysis_service,
                "predict_network_flows",
                side_effect=AssertionError("prediction must not rerun"),
            ),
        ):
            second_status, second = self.request(
                "POST", f"/network/datasets/{dataset_id}/analyze"
            )
        self.assertEqual(second_status, 200, second)
        self.assertTrue(second["reused_existing"])
        with self.Session() as session:
            self.assertEqual(session.query(NetworkPrediction).count(), 2)
            self.assertEqual(session.query(NetworkIncident).count(), 1)
            incident = session.query(NetworkIncident).one()
            session.delete(incident)
            session.commit()

        conflict_status, conflict = self.request(
            "POST", f"/network/datasets/{dataset_id}/analyze"
        )
        self.assertEqual(conflict_status, 409, conflict)
        self.assertIn("inconsistent", conflict["detail"].lower())

        missing_predictions_id = self.seed_dataset(
            labelled=False,
            rows=[feature_record(20)],
            filename="missing-predictions.csv",
        )
        with self.Session() as session:
            dataset = session.get(NetworkDataset, missing_predictions_id)
            dataset.analysis_status = "completed"
            session.commit()
        missing_status, missing = self.request(
            "POST",
            f"/network/datasets/{missing_predictions_id}/analyze",
        )
        self.assertEqual(missing_status, 409, missing)
        self.assertIn("inconsistent", missing["detail"].lower())

    def test_failure_rolls_back_all_children_marks_failed_and_allows_retry(self):
        self.authenticate()
        dataset_id = self.seed_dataset(
            labelled=True,
            rows=[
                labelled_row(20, "normal"),
                labelled_row(38, "normal"),
                labelled_row(60, "back"),
                labelled_row(90, "satan"),
            ],
        )
        original_persist = analysis_service._persist_analysis_batch
        persist_calls = 0

        def fail_after_first_batch(db, current_dataset_id, predictions, incidents):
            nonlocal persist_calls
            persist_calls += 1
            if persist_calls == 1:
                original_persist(
                    db,
                    current_dataset_id,
                    predictions,
                    incidents,
                )
                return
            raise RuntimeError("forced internal database detail")

        load_patch, predict_patch, summary_patch = self.analysis_patches()
        with (
            patch.object(analysis_service, "ANALYSIS_BATCH_SIZE", 2),
            patch.object(
                analysis_service,
                "_persist_analysis_batch",
                side_effect=fail_after_first_batch,
            ),
            load_patch,
            predict_patch,
            summary_patch,
        ):
            status, response = self.request(
                "POST", f"/network/datasets/{dataset_id}/analyze"
            )
        self.assertEqual(status, 500, response)
        self.assertNotIn("forced internal", response["detail"])
        with self.Session() as session:
            dataset = session.get(NetworkDataset, dataset_id)
            self.assertEqual(dataset.analysis_status, "failed")
            self.assertIsNotNone(dataset.analysis_completed_at)
            self.assertIn("no partial results", dataset.analysis_error.lower())
            self.assertEqual(session.query(NetworkPrediction).count(), 0)
            self.assertEqual(session.query(NetworkIncident).count(), 0)

        load_patch, predict_patch, summary_patch = self.analysis_patches()
        with load_patch, predict_patch, summary_patch:
            retry_status, retry = self.request(
                "POST", f"/network/datasets/{dataset_id}/analyze"
            )
        self.assertEqual(retry_status, 200, retry)
        self.assertEqual(retry["analysis_status"], "completed")
        with self.Session() as session:
            self.assertEqual(session.query(NetworkPrediction).count(), 4)
            self.assertEqual(session.query(NetworkIncident).count(), 3)

    def test_summary_endpoint_reports_each_state_without_inference(self):
        self.authenticate()
        dataset_id = self.seed_dataset(
            labelled=False,
            rows=[feature_record(20), feature_record(90)],
        )
        with patch.object(
            analysis_service,
            "predict_network_flows",
            side_effect=AssertionError("summary must not infer"),
        ):
            uploaded_status, uploaded = self.request(
                "GET", f"/network/datasets/{dataset_id}/analysis"
            )
        self.assertEqual(uploaded_status, 200, uploaded)
        self.assertEqual(uploaded["analysis_status"], "uploaded")
        self.assertEqual(uploaded["total_predictions"], 0)

        with self.Session() as session:
            dataset = session.get(NetworkDataset, dataset_id)
            dataset.analysis_status = "processing"
            session.commit()
        processing_status, processing = self.request(
            "GET", f"/network/datasets/{dataset_id}/analysis"
        )
        self.assertEqual(processing_status, 200, processing)
        self.assertEqual(processing["analysis_status"], "processing")

        with self.Session() as session:
            dataset = session.get(NetworkDataset, dataset_id)
            dataset.analysis_status = "failed"
            dataset.analysis_error = "Safe failure message."
            session.commit()
        failed_status, failed = self.request(
            "GET", f"/network/datasets/{dataset_id}/analysis"
        )
        self.assertEqual(failed_status, 200, failed)
        self.assertEqual(failed["analysis_status"], "failed")
        self.assertEqual(failed["analysis_error"], "Safe failure message.")

        load_patch, predict_patch, summary_patch = self.analysis_patches()
        with load_patch, predict_patch, summary_patch:
            completed_status, completed = self.request(
                "POST", f"/network/datasets/{dataset_id}/analyze"
            )
        self.assertEqual(completed_status, 200, completed)
        summary_status, summary = self.request(
            "GET", f"/network/datasets/{dataset_id}/analysis"
        )
        self.assertEqual(summary_status, 200, summary)
        self.assertEqual(summary["analysis_status"], "completed")
        self.assertFalse(summary["reused_existing"])
        unknown_status, _ = self.request(
            "GET", "/network/datasets/99999/analysis"
        )
        self.assertEqual(unknown_status, 404)

    def test_model_load_failure_is_safe_and_persists_failed_status(self):
        self.authenticate()
        dataset_id = self.seed_dataset(
            labelled=False,
            rows=[feature_record(20)],
        )

        class FinalDetectorError(RuntimeError):
            pass

        with patch.object(
            analysis_service,
            "load_final_detector",
            side_effect=FinalDetectorError(
                "D:/private/path/hash mismatch and secret details"
            ),
        ):
            status, response = self.request(
                "POST", f"/network/datasets/{dataset_id}/analyze"
            )
        self.assertEqual(status, 500, response)
        self.assertIn("could not be loaded or verified", response["detail"])
        self.assertNotIn("D:/", response["detail"])
        self.assertNotIn("secret", response["detail"])
        with self.Session() as session:
            dataset = session.get(NetworkDataset, dataset_id)
            self.assertEqual(dataset.analysis_status, "failed")
            self.assertEqual(dataset.analysis_error, response["detail"])
            self.assertEqual(session.query(NetworkPrediction).count(), 0)
            self.assertEqual(session.query(NetworkIncident).count(), 0)


if __name__ == "__main__":
    unittest.main()
