"""Focused tests for persisted-only N4D network read and workflow APIs."""

from __future__ import annotations

import asyncio
import json
import unittest
from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.auth.service import get_current_user
from backend.app.database import models  # noqa: F401 - register all tables
from backend.app.database.network_models import (
    NetworkDataset,
    NetworkFlow,
    NetworkIncident,
    NetworkPrediction,
)
from backend.app.database.session import Base, get_db
from backend.app.network import analysis_service, incident_service
from backend.app.network.routes import router
from backend.app.tests.test_network_ingestion import (
    asgi_request,
    feature_record,
)

MODEL_NAME = "Recall-oriented Random Forest"
MODEL_VERSION = "persisted-test-artifact-sha256"
BOUNDARY_PROBABILITIES = [
    0.00,
    0.10,
    0.20,
    0.30,
    0.38,
    0.50,
    0.60,
    0.75,
    0.90,
    1.00,
]


def forbidden_call(*args, **kwargs):
    """Fail if a persisted-only endpoint reaches inference or fitting."""
    del args, kwargs
    raise AssertionError("N4D read/update endpoint invoked inference or fitting.")


@contextmanager
def persisted_only_guards():
    """Guard every forbidden model-loading, prediction, and fitting entry point."""
    with ExitStack() as stack:
        for target, name in [
            (analysis_service, "predict_network_flows"),
            (analysis_service, "load_final_detector"),
            (Pipeline, "fit"),
            (RandomForestClassifier, "fit"),
        ]:
            stack.enter_context(patch.object(target, name, new=forbidden_call))
        yield


def severity_for_probability(probability: float) -> str:
    if probability >= 0.90:
        return "critical"
    if probability >= 0.75:
        return "high"
    if probability >= 0.60:
        return "medium"
    return "low"


class NetworkReadApiTest(unittest.TestCase):
    """Verify authenticated SQL-backed reads and persistent status updates."""

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
        self.ids = self._seed_persisted_fixtures()

    def authenticate(self, role: str = "analyst") -> None:
        user = SimpleNamespace(id=1, username=f"{role}-user", role=role)
        self.app.dependency_overrides[get_current_user] = lambda: user

    def request(
        self,
        method: str,
        path: str,
        *,
        query: dict | None = None,
        json_body: dict | None = None,
    ) -> tuple[int, dict]:
        body = b""
        headers = None
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            headers = {"content-type": "application/json"}
        with persisted_only_guards():
            return asyncio.run(
                asgi_request(
                    self.app,
                    method,
                    path,
                    body=body,
                    headers=headers,
                    query=query,
                )
            )

    def _flow(
        self,
        dataset_id: int,
        row_number: int,
        *,
        protocol: str,
        service: str,
        flag: str,
        actual_label: str | None,
        actual_family: str | None,
        difficulty_level: int | None,
    ) -> NetworkFlow:
        values = feature_record(row_number)
        values.update(
            {
                "protocol_type": protocol,
                "service": service,
                "flag": flag,
                "src_bytes": 1000 + row_number,
                "dst_bytes": 2000 + row_number,
                "num_failed_logins": row_number % 3,
                "logged_in": row_number % 2,
                "serror_rate": row_number / 100,
                "rerror_rate": row_number / 200,
            }
        )
        return NetworkFlow(
            dataset_id=dataset_id,
            row_number=row_number,
            **values,
            actual_label=actual_label,
            actual_family=actual_family,
            difficulty_level=difficulty_level,
        )

    def _seed_completed_dataset(
        self,
        session,
        *,
        filename: str,
        probabilities: list[float],
        labelled: bool,
        create_incidents: bool = True,
    ) -> tuple[int, list[int]]:
        started_at = datetime(2026, 7, 1, 10, 0, 0)
        dataset = NetworkDataset(
            filename=filename,
            total_records=len(probabilities),
            has_ground_truth=labelled,
            source_type=(
                "nsl_kdd_labelled" if labelled else "nsl_kdd_inference"
            ),
            analysis_status="completed",
            model_name=MODEL_NAME,
            model_threshold=0.38,
            analysis_started_at=started_at,
            analysis_completed_at=started_at + timedelta(seconds=5),
        )
        session.add(dataset)
        session.flush()

        labels = [
            ("normal", "normal"),
            ("normal", "normal"),
            ("back", "dos"),
            ("normal", "normal"),
            ("normal", "normal"),
            ("satan", "probe"),
            ("guess_passwd", "r2l"),
            ("buffer_overflow", "u2r"),
            ("neptune", "dos"),
            ("portsweep", "probe"),
        ]
        services = [
            "http",
            "http",
            "http",
            "http",
            "ftp_data",
            "ftp_data",
            "ftp_data",
            "smtp",
            "smtp",
            "domain_u",
        ]
        statuses = [
            "open",
            "investigating",
            "resolved",
            "false_positive",
            "open",
            "open",
        ]
        incident_ids = []
        incident_index = 0
        for index, probability in enumerate(probabilities):
            label, family = (
                labels[index]
                if labelled
                else (None, None)
            )
            flow = self._flow(
                dataset.id,
                index + 1,
                protocol="tcp" if index < 6 else "udp",
                service=(
                    services[index]
                    if index < len(services)
                    else f"service_{index}"
                ),
                flag="SF" if index % 2 == 0 else "S0",
                actual_label=label,
                actual_family=family,
                difficulty_level=21 - index if labelled else None,
            )
            session.add(flow)
            session.flush()
            predicted_binary = int(probability >= 0.38)
            actual_binary = (
                None
                if not labelled
                else int(label != "normal")
            )
            prediction = NetworkPrediction(
                dataset_id=dataset.id,
                flow_id=flow.id,
                created_at=started_at + timedelta(milliseconds=index),
                rf_attack_probability=probability,
                predicted_binary=predicted_binary,
                predicted_class=(
                    "attack" if predicted_binary else "normal"
                ),
                threshold_used=0.38,
                model_name=MODEL_NAME,
                model_version=MODEL_VERSION,
                actual_binary=actual_binary,
                is_correct=(
                    None
                    if actual_binary is None
                    else actual_binary == predicted_binary
                ),
            )
            session.add(prediction)
            session.flush()
            if create_incidents and predicted_binary == 1:
                incident = NetworkIncident(
                    dataset_id=dataset.id,
                    flow_id=flow.id,
                    prediction_id=prediction.id,
                    created_at=started_at + timedelta(seconds=index),
                    incident_type="Predicted Network Intrusion",
                    severity=severity_for_probability(probability),
                    risk_score=probability * 100,
                    evidence=(
                        "Persisted model signal using real "
                        f"protocol={flow.protocol_type}, "
                        f"service={flow.service}, flag={flow.flag}, "
                        f"src_bytes={flow.src_bytes} for row {flow.row_number}."
                    ),
                    recommended_action=(
                        "Review related traffic and validate the connection "
                        "before remediation."
                    ),
                    status=statuses[incident_index % len(statuses)],
                    protocol_type=flow.protocol_type,
                    service=flow.service,
                    flag=flow.flag,
                    actual_label=flow.actual_label,
                    actual_family=flow.actual_family,
                )
                session.add(incident)
                session.flush()
                incident_ids.append(incident.id)
                incident_index += 1
        return dataset.id, incident_ids

    def _seed_unanalysed_dataset(
        self,
        session,
        *,
        status: str,
        error: str | None = None,
    ) -> int:
        dataset = NetworkDataset(
            filename=f"{status}.csv",
            total_records=2 if status == "uploaded" else 0,
            has_ground_truth=False,
            source_type="nsl_kdd_inference",
            analysis_status=status,
            analysis_error=error,
        )
        session.add(dataset)
        session.flush()
        if status == "uploaded":
            session.add_all(
                [
                    self._flow(
                        dataset.id,
                        row_number,
                        protocol="tcp",
                        service="http",
                        flag="SF",
                        actual_label=None,
                        actual_family=None,
                        difficulty_level=None,
                    )
                    for row_number in [1, 2]
                ]
            )
        return dataset.id

    def _seed_persisted_fixtures(self) -> dict:
        with self.Session() as session:
            labelled_id, labelled_incidents = self._seed_completed_dataset(
                session,
                filename="labelled.csv",
                probabilities=BOUNDARY_PROBABILITIES,
                labelled=True,
            )
            inference_id, inference_incidents = self._seed_completed_dataset(
                session,
                filename="inference.csv",
                probabilities=[0.20, 0.80],
                labelled=False,
            )
            no_incident_id, _ = self._seed_completed_dataset(
                session,
                filename="no-incidents.csv",
                probabilities=[0.10, 0.20],
                labelled=False,
                create_incidents=False,
            )
            uploaded_id = self._seed_unanalysed_dataset(
                session, status="uploaded"
            )
            failed_id = self._seed_unanalysed_dataset(
                session,
                status="failed",
                error="Safe persisted analysis error.",
            )
            session.commit()
            return {
                "labelled": labelled_id,
                "labelled_incidents": labelled_incidents,
                "inference": inference_id,
                "inference_incident": inference_incidents[0],
                "no_incident": no_incident_id,
                "uploaded": uploaded_id,
                "failed": failed_id,
            }

    def test_authentication_unknown_and_unanalysed_states(self):
        incident_id = self.ids["labelled_incidents"][0]
        endpoints = [
            ("GET", f"/network/datasets/{self.ids['labelled']}/dashboard", None),
            ("GET", f"/network/datasets/{self.ids['labelled']}/analytics", None),
            ("GET", f"/network/datasets/{self.ids['labelled']}/incidents", None),
            ("GET", f"/network/incidents/{incident_id}", None),
            (
                "PATCH",
                f"/network/incidents/{incident_id}/status",
                {"status": "investigating"},
            ),
        ]
        for method, path, body in endpoints:
            with self.subTest(path=path):
                status, _ = self.request(method, path, json_body=body)
                self.assertEqual(status, 401)

        self.authenticate()
        for path in [
            "/network/datasets/99999/dashboard",
            "/network/datasets/99999/analytics",
            "/network/datasets/99999/incidents",
            "/network/incidents/99999",
        ]:
            status, _ = self.request("GET", path)
            self.assertEqual(status, 404)
        patch_status, _ = self.request(
            "PATCH",
            "/network/incidents/99999/status",
            json_body={"status": "open"},
        )
        self.assertEqual(patch_status, 404)

        uploaded_status, uploaded = self.request(
            "GET",
            f"/network/datasets/{self.ids['uploaded']}/dashboard",
        )
        self.assertEqual(uploaded_status, 200, uploaded)
        self.assertEqual(uploaded["dataset"]["analysis_status"], "uploaded")
        self.assertEqual(uploaded["dataset"]["total_flows"], 2)
        self.assertEqual(uploaded["prediction_kpis"]["total_predictions"], 0)
        self.assertEqual(uploaded["incident_kpis"]["total_incidents"], 0)
        self.assertIsNone(uploaded["model"])
        self.assertIsNone(uploaded["benchmark_metrics"])
        self.assertEqual(uploaded["priority_incidents"], [])

        analytics_status, analytics = self.request(
            "GET",
            f"/network/datasets/{self.ids['uploaded']}/analytics",
        )
        self.assertEqual(analytics_status, 200, analytics)
        self.assertEqual(analytics["prediction_distribution"], [])
        self.assertEqual(analytics["probability_histogram"], [])

        failed_status, failed = self.request(
            "GET", f"/network/datasets/{self.ids['failed']}/dashboard"
        )
        self.assertEqual(failed_status, 200, failed)
        self.assertEqual(failed["dataset"]["analysis_status"], "failed")
        self.assertEqual(
            failed["dataset"]["analysis_error"],
            "Safe persisted analysis error.",
        )

    def test_dashboard_exact_kpis_benchmarks_and_priority_order(self):
        self.authenticate("admin")
        status, dashboard = self.request(
            "GET",
            f"/network/datasets/{self.ids['labelled']}/dashboard",
        )
        self.assertEqual(status, 200, dashboard)
        self.assertEqual(dashboard["dataset"]["total_flows"], 10)
        self.assertTrue(dashboard["dataset"]["has_ground_truth"])
        self.assertEqual(dashboard["model"]["model_name"], MODEL_NAME)
        self.assertEqual(dashboard["model"]["model_version"], MODEL_VERSION)
        self.assertEqual(dashboard["model"]["threshold_probability"], 0.38)
        self.assertEqual(
            dashboard["prediction_kpis"],
            {
                "total_predictions": 10,
                "predicted_normal": 4,
                "predicted_attack": 6,
                "predicted_attack_percentage": 60.0,
                "minimum_attack_probability": 0.0,
                "maximum_attack_probability": 1.0,
                "mean_attack_probability": 0.47300000000000003,
            },
        )
        self.assertEqual(
            dashboard["incident_kpis"],
            {
                "total_incidents": 6,
                "open_incidents": 3,
                "investigating_incidents": 1,
                "resolved_incidents": 1,
                "false_positive_status_incidents": 1,
                "critical_incidents": 2,
                "high_incidents": 1,
                "medium_incidents": 1,
                "low_incidents": 2,
                "highest_risk_score": 100.0,
            },
        )
        benchmark = dashboard["benchmark_metrics"]
        self.assertEqual(
            [
                benchmark["true_negatives"],
                benchmark["false_positives"],
                benchmark["false_negatives"],
                benchmark["true_positives"],
            ],
            [3, 1, 1, 5],
        )
        self.assertAlmostEqual(benchmark["accuracy"], 0.8)
        self.assertAlmostEqual(benchmark["precision"], 5 / 6)
        self.assertAlmostEqual(benchmark["recall"], 5 / 6)
        self.assertAlmostEqual(benchmark["f1"], 5 / 6)
        self.assertAlmostEqual(benchmark["f2"], 5 / 6)
        self.assertAlmostEqual(benchmark["false_positive_rate"], 0.25)
        self.assertAlmostEqual(benchmark["false_negative_rate"], 1 / 6)
        priorities = dashboard["priority_incidents"]
        self.assertEqual(len(priorities), 5)
        self.assertEqual(
            [item["risk_score"] for item in priorities],
            [100.0, 90.0, 75.0, 60.0, 50.0],
        )

        inference_status, inference = self.request(
            "GET",
            f"/network/datasets/{self.ids['inference']}/dashboard",
        )
        self.assertEqual(inference_status, 200, inference)
        self.assertIsNone(inference["benchmark_metrics"])

    def test_analytics_distributions_limits_and_histogram_boundaries(self):
        self.authenticate()
        status, analytics = self.request(
            "GET",
            f"/network/datasets/{self.ids['labelled']}/analytics",
            query={"service_limit": 2},
        )
        self.assertEqual(status, 200, analytics)
        self.assertEqual(
            [
                (item["predicted_class"], item["record_count"], item["percentage"])
                for item in analytics["prediction_distribution"]
            ],
            [("normal", 4, 40.0), ("attack", 6, 60.0)],
        )
        self.assertEqual(
            sum(item["total_records"] for item in analytics["protocol_distribution"]),
            10,
        )
        self.assertEqual(
            [item["protocol"] for item in analytics["protocol_distribution"]],
            ["tcp", "udp"],
        )
        self.assertEqual(
            [
                (item["service"], item["total_records"])
                for item in analytics["service_distribution"]
            ],
            [("http", 4), ("ftp_data", 3)],
        )
        self.assertEqual(
            sum(item["total_records"] for item in analytics["flag_distribution"]),
            10,
        )
        self.assertEqual(
            analytics["severity_distribution"],
            {"critical": 2, "high": 1, "medium": 1, "low": 2},
        )
        histogram_counts = [
            item["record_count"] for item in analytics["probability_histogram"]
        ]
        self.assertEqual(histogram_counts, [1, 1, 1, 1, 1, 1, 1, 1, 2])
        self.assertEqual(sum(histogram_counts), 10)
        self.assertEqual(
            [item["label"] for item in analytics["probability_histogram"]],
            [
                "0.00–0.10",
                "0.10–0.20",
                "0.20–0.30",
                "0.30–0.38",
                "0.38–0.50",
                "0.50–0.60",
                "0.60–0.75",
                "0.75–0.90",
                "0.90–1.00",
            ],
        )
        self.assertEqual(
            {
                item["value"]: item["record_count"]
                for item in analytics["actual_family_distribution"]
            },
            {"normal": 4, "dos": 2, "probe": 2, "r2l": 1, "u2r": 1},
        )
        self.assertEqual(
            {
                item["value"]: item["record_count"]
                for item in analytics["correctness_distribution"]
            },
            {"correct": 8, "incorrect": 2},
        )

        _, inference = self.request(
            "GET",
            f"/network/datasets/{self.ids['inference']}/analytics",
        )
        self.assertIsNone(inference["actual_family_distribution"])
        self.assertIsNone(inference["correctness_distribution"])
        self.assertIsNone(inference["benchmark_metrics"])

    def test_incident_queue_filters_search_pagination_and_join_count(self):
        self.authenticate()
        path = f"/network/datasets/{self.ids['labelled']}/incidents"
        select_statements = 0

        def count_selects(
            connection, cursor, statement, parameters, context, executemany
        ):
            del connection, cursor, parameters, context, executemany
            nonlocal select_statements
            if statement.lstrip().upper().startswith("SELECT"):
                select_statements += 1

        event.listen(self.engine, "before_cursor_execute", count_selects)
        try:
            status, page = self.request("GET", path)
        finally:
            event.remove(self.engine, "before_cursor_execute", count_selects)
        self.assertEqual(status, 200, page)
        self.assertLessEqual(select_statements, 3)
        self.assertEqual(page["total"], 6)
        self.assertEqual(
            [item["risk_score"] for item in page["items"]],
            [100.0, 90.0, 75.0, 60.0, 50.0, 38.0],
        )
        self.assertTrue(all("row_number" in item for item in page["items"]))
        self.assertTrue(
            all("rf_attack_probability" in item for item in page["items"])
        )

        _, open_page = self.request("GET", path, query={"status": "open"})
        self.assertEqual(open_page["total"], 3)
        _, critical_page = self.request(
            "GET", path, query={"severity": "critical"}
        )
        self.assertEqual(critical_page["total"], 2)
        _, search_page = self.request("GET", path, query={"search": "SmTp"})
        self.assertEqual(search_page["total"], 2)
        _, combined = self.request(
            "GET",
            path,
            query={
                "status": "open",
                "severity": "critical",
                "search": "UDP",
            },
        )
        self.assertEqual(combined["total"], 2)
        self.assertEqual(
            combined["filters"],
            {"status": "open", "severity": "critical", "search": "UDP"},
        )
        _, paged = self.request(
            "GET", path, query={"limit": 2, "offset": 1}
        )
        self.assertEqual(paged["total"], 6)
        self.assertEqual(
            [item["risk_score"] for item in paged["items"]],
            [90.0, 75.0],
        )

        empty_status, empty = self.request(
            "GET",
            f"/network/datasets/{self.ids['no_incident']}/incidents",
        )
        self.assertEqual(empty_status, 200, empty)
        self.assertEqual(empty["total"], 0)
        self.assertEqual(empty["items"], [])

        invalid_status, _ = self.request(
            "GET", path, query={"status": "invalid"}
        )
        invalid_severity, _ = self.request(
            "GET", path, query={"severity": "urgent"}
        )
        self.assertEqual(invalid_status, 400)
        self.assertEqual(invalid_severity, 400)

    def test_incident_detail_returns_real_joined_context(self):
        self.authenticate()
        with self.Session() as session:
            labelled_incident = (
                session.query(NetworkIncident)
                .filter(
                    NetworkIncident.dataset_id == self.ids["labelled"],
                    NetworkIncident.risk_score == 60,
                )
                .one()
            )
            labelled_incident_id = labelled_incident.id

        status, detail = self.request(
            "GET", f"/network/incidents/{labelled_incident_id}"
        )
        self.assertEqual(status, 200, detail)
        self.assertEqual(detail["risk_score"], 60.0)
        self.assertEqual(detail["rf_attack_probability"], 0.6)
        self.assertIn("protocol=", detail["evidence"])
        self.assertIn("before remediation", detail["recommended_action"])
        self.assertEqual(detail["prediction"]["predicted_class"], "attack")
        self.assertEqual(
            detail["prediction"]["threshold_used_probability"], 0.38
        )
        self.assertEqual(detail["prediction"]["actual_binary"], 1)
        self.assertTrue(detail["prediction"]["is_correct"])
        flow = detail["flow_context"]
        self.assertEqual(flow["row_number"], detail["row_number"])
        self.assertEqual(flow["protocol_type"], detail["protocol_type"])
        self.assertEqual(flow["service"], detail["service"])
        self.assertIsNotNone(flow["actual_label"])
        self.assertIsNotNone(flow["actual_family"])
        self.assertIsNotNone(flow["difficulty_level"])
        self.assertNotIn("ip_address", detail)
        self.assertNotIn("endpoint", detail)
        self.assertNotIn("predicted_attack_family", detail)

        _, inference = self.request(
            "GET",
            f"/network/incidents/{self.ids['inference_incident']}",
        )
        self.assertIsNone(inference["actual_label"])
        self.assertIsNone(inference["actual_family"])
        self.assertIsNone(inference["prediction"]["actual_binary"])
        self.assertIsNone(inference["prediction"]["is_correct"])
        self.assertIsNone(inference["flow_context"]["difficulty_level"])

    def test_status_updates_persist_only_status_and_rollback_on_failure(self):
        self.authenticate("analyst")
        incident_id = self.ids["labelled_incidents"][0]
        with self.Session() as session:
            incident = session.get(NetworkIncident, incident_id)
            unchanged = {
                "risk_score": incident.risk_score,
                "severity": incident.severity,
                "evidence": incident.evidence,
                "recommended_action": incident.recommended_action,
            }

        for workflow_status in [
            "investigating",
            "resolved",
            "false_positive",
            "open",
        ]:
            status, response = self.request(
                "PATCH",
                f"/network/incidents/{incident_id}/status",
                json_body={"status": workflow_status},
            )
            self.assertEqual(status, 200, response)
            self.assertEqual(response["status"], workflow_status)
            with self.Session() as session:
                persisted = session.get(NetworkIncident, incident_id)
                self.assertEqual(persisted.status, workflow_status)
                for field, value in unchanged.items():
                    self.assertEqual(getattr(persisted, field), value)

        detail_status, detail = self.request(
            "GET", f"/network/incidents/{incident_id}"
        )
        self.assertEqual(detail_status, 200, detail)
        self.assertEqual(detail["status"], "open")

        invalid_status, _ = self.request(
            "PATCH",
            f"/network/incidents/{incident_id}/status",
            json_body={"status": "closed"},
        )
        self.assertEqual(invalid_status, 422)

        with patch.object(
            incident_service,
            "_commit_status_change",
            side_effect=RuntimeError("private database detail"),
        ):
            failed_status, failed = self.request(
                "PATCH",
                f"/network/incidents/{incident_id}/status",
                json_body={"status": "resolved"},
            )
        self.assertEqual(failed_status, 500, failed)
        self.assertNotIn("private database", failed["detail"])
        with self.Session() as session:
            persisted = session.get(NetworkIncident, incident_id)
            self.assertEqual(persisted.status, "open")
            for field, value in unchanged.items():
                self.assertEqual(getattr(persisted, field), value)


if __name__ == "__main__":
    unittest.main()
