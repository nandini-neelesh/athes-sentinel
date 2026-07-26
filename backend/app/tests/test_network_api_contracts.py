"""Focused frontend-facing response-contract tests for network mode."""

from __future__ import annotations

import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.auth.service import get_current_user
from backend.app.database import models  # noqa: F401 - register all tables
from backend.app.database.session import Base, get_db
from backend.app.network import analysis_service
from backend.app.network.routes import router
from backend.app.tests.test_network_analysis import (
    fake_load_final_detector,
    fake_predict_network_flows,
    fake_summarize_predictions,
    labelled_row,
    no_fitting_allowed,
)
from backend.app.tests.test_network_ingestion import (
    asgi_request,
    dataset_bytes,
    feature_record,
    multipart_body,
)


DATASET_KEYS = {
    "id",
    "filename",
    "uploaded_at",
    "total_records",
    "has_ground_truth",
    "source_type",
    "analysis_status",
    "analysis_error",
    "model_name",
    "model_threshold",
    "analysis_started_at",
    "analysis_completed_at",
}
UPLOAD_KEYS = DATASET_KEYS | {
    "label_distribution",
    "attack_family_distribution",
    "protocol_distribution",
    "service_unique_count",
    "flag_distribution",
}
DASHBOARD_KEYS = {
    "dataset",
    "model",
    "prediction_kpis",
    "incident_kpis",
    "benchmark_metrics",
    "priority_incidents",
}
COMPACT_INCIDENT_KEYS = {
    "incident_id",
    "dataset_id",
    "flow_id",
    "prediction_id",
    "row_number",
    "created_at",
    "incident_type",
    "severity",
    "risk_score",
    "status",
    "protocol_type",
    "service",
    "flag",
    "actual_label",
    "actual_family",
    "rf_attack_probability",
    "evidence_preview",
}
DETAIL_KEYS = COMPACT_INCIDENT_KEYS | {
    "evidence",
    "recommended_action",
    "prediction",
    "flow_context",
}


class NetworkApiContractTest(unittest.TestCase):
    """Catch accidental backend/frontend network-contract drift."""

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
        user = SimpleNamespace(id=1, username="contract-user", role="analyst")
        cls.app.dependency_overrides[get_current_user] = lambda: user

    @classmethod
    def tearDownClass(cls):
        cls.app.dependency_overrides.clear()
        cls.engine.dispose()

    def setUp(self):
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes = b"",
        headers: dict[str, str] | None = None,
        query: dict | None = None,
    ) -> tuple[int, dict]:
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

    def upload(self, rows: list[dict], *, labelled: bool) -> dict:
        filename = "labelled.csv" if labelled else "inference.csv"
        content = dataset_bytes(labelled, True, rows=rows)
        body, content_type = multipart_body(filename, content)
        status, response = self.request(
            "POST",
            "/network/datasets/upload",
            body=body,
            headers={"content-type": content_type},
        )
        self.assertEqual(status, 201, response)
        return response

    def analyse(self, dataset_id: int) -> dict:
        with (
            no_fitting_allowed(),
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
        ):
            status, response = self.request(
                "POST", f"/network/datasets/{dataset_id}/analyze"
            )
        self.assertEqual(status, 200, response)
        return response

    def assert_required_keys(self, value: dict, required: set[str]) -> None:
        self.assertTrue(required.issubset(value), (required - value.keys(), value))

    def test_labelled_frontend_contracts(self):
        upload = self.upload(
            [
                labelled_row(20, "normal"),
                labelled_row(38, "normal"),
                labelled_row(60, "back"),
                labelled_row(75, "neptune"),
                labelled_row(90, "satan"),
            ],
            labelled=True,
        )
        self.assert_required_keys(upload, UPLOAD_KEYS)
        self.assertIsInstance(upload["id"], int)
        self.assertIsInstance(upload["total_records"], int)
        self.assertIsInstance(upload["has_ground_truth"], bool)
        self.assertIsInstance(upload["label_distribution"], list)
        dataset_id = upload["id"]

        status, uploaded_dashboard = self.request(
            "GET", f"/network/datasets/{dataset_id}/dashboard"
        )
        self.assertEqual(status, 200, uploaded_dashboard)
        self.assert_required_keys(uploaded_dashboard, DASHBOARD_KEYS)
        self.assertEqual(
            uploaded_dashboard["dataset"]["analysis_status"], "uploaded"
        )
        self.assertIsNone(uploaded_dashboard["model"])
        self.assertIsNone(uploaded_dashboard["benchmark_metrics"])
        self.assertEqual(
            uploaded_dashboard["prediction_kpis"]["total_predictions"], 0
        )

        analysis = self.analyse(dataset_id)
        self.assert_required_keys(
            analysis,
            {
                "dataset_id",
                "filename",
                "total_flows",
                "total_predictions",
                "predicted_normal",
                "predicted_attack",
                "predicted_attack_percentage",
                "total_incidents",
                "severity_counts",
                "minimum_probability",
                "maximum_probability",
                "mean_probability",
                "model_name",
                "model_version",
                "threshold",
                "analysis_status",
                "analysis_error",
                "analysis_started_at",
                "analysis_completed_at",
                "reused_existing",
                "benchmark_metrics",
            },
        )

        status, dashboard = self.request(
            "GET", f"/network/datasets/{dataset_id}/dashboard"
        )
        self.assertEqual(status, 200, dashboard)
        self.assert_required_keys(dashboard, DASHBOARD_KEYS)
        self.assert_required_keys(
            dashboard["dataset"],
            {
                "dataset_id",
                "filename",
                "uploaded_at",
                "total_flows",
                "has_ground_truth",
                "source_type",
                "analysis_status",
                "analysis_error",
                "analysis_started_at",
                "analysis_completed_at",
            },
        )
        self.assert_required_keys(
            dashboard["model"],
            {"model_name", "model_version", "threshold_probability"},
        )
        self.assert_required_keys(
            dashboard["prediction_kpis"],
            {
                "total_predictions",
                "predicted_normal",
                "predicted_attack",
                "predicted_attack_percentage",
                "minimum_attack_probability",
                "maximum_attack_probability",
                "mean_attack_probability",
            },
        )
        self.assert_required_keys(
            dashboard["incident_kpis"],
            {
                "total_incidents",
                "open_incidents",
                "investigating_incidents",
                "resolved_incidents",
                "false_positive_status_incidents",
                "critical_incidents",
                "high_incidents",
                "medium_incidents",
                "low_incidents",
                "highest_risk_score",
            },
        )
        self.assertIsInstance(dashboard["priority_incidents"], list)

        status, analytics = self.request(
            "GET",
            f"/network/datasets/{dataset_id}/analytics",
            query={"service_limit": 10},
        )
        self.assertEqual(status, 200, analytics)
        self.assert_required_keys(
            analytics,
            {
                "dataset_id",
                "analysis_status",
                "prediction_distribution",
                "protocol_distribution",
                "service_distribution",
                "flag_distribution",
                "severity_distribution",
                "probability_histogram",
                "actual_family_distribution",
                "correctness_distribution",
                "benchmark_metrics",
            },
        )
        self.assertIsInstance(analytics["probability_histogram"], list)
        self.assertIsInstance(analytics["actual_family_distribution"], list)
        self.assertIsInstance(analytics["correctness_distribution"], list)
        self.assertIsInstance(analytics["benchmark_metrics"], dict)

        status, queue = self.request(
            "GET",
            f"/network/datasets/{dataset_id}/incidents",
            query={"limit": 25, "offset": 0, "status": "open"},
        )
        self.assertEqual(status, 200, queue)
        self.assert_required_keys(
            queue,
            {"dataset_id", "items", "total", "limit", "offset", "filters"},
        )
        self.assertIsInstance(queue["total"], int)
        self.assertIsInstance(queue["items"], list)
        self.assertGreater(len(queue["items"]), 0)
        self.assert_required_keys(queue["items"][0], COMPACT_INCIDENT_KEYS)

        incident_id = queue["items"][0]["incident_id"]
        status, detail = self.request(
            "GET", f"/network/incidents/{incident_id}"
        )
        self.assertEqual(status, 200, detail)
        self.assert_required_keys(detail, DETAIL_KEYS)
        self.assert_required_keys(
            detail["prediction"],
            {
                "rf_attack_probability",
                "predicted_class",
                "threshold_used_probability",
                "model_name",
                "model_version",
                "actual_binary",
                "is_correct",
            },
        )
        self.assert_required_keys(
            detail["flow_context"],
            {
                "row_number",
                "duration",
                "protocol_type",
                "service",
                "flag",
                "src_bytes",
                "dst_bytes",
                "num_failed_logins",
                "logged_in",
                "count",
                "srv_count",
                "actual_label",
                "actual_family",
                "difficulty_level",
            },
        )

        status, updated = self.request(
            "PATCH",
            f"/network/incidents/{incident_id}/status",
            body=json.dumps({"status": "investigating"}).encode("utf-8"),
            headers={"content-type": "application/json"},
        )
        self.assertEqual(status, 200, updated)
        self.assert_required_keys(updated, DETAIL_KEYS)
        self.assertEqual(updated["status"], "investigating")

    def test_inference_only_contract_nullability(self):
        upload = self.upload(
            [feature_record(20), feature_record(90)],
            labelled=False,
        )
        self.assert_required_keys(upload, UPLOAD_KEYS)
        self.assertFalse(upload["has_ground_truth"])
        self.assertEqual(upload["label_distribution"], [])
        self.assertEqual(upload["attack_family_distribution"], [])
        dataset_id = upload["id"]

        analysis = self.analyse(dataset_id)
        self.assertIsNone(analysis["benchmark_metrics"])

        status, dashboard = self.request(
            "GET", f"/network/datasets/{dataset_id}/dashboard"
        )
        self.assertEqual(status, 200, dashboard)
        self.assertIsNone(dashboard["benchmark_metrics"])

        status, analytics = self.request(
            "GET", f"/network/datasets/{dataset_id}/analytics"
        )
        self.assertEqual(status, 200, analytics)
        self.assertIsNone(analytics["actual_family_distribution"])
        self.assertIsNone(analytics["correctness_distribution"])
        self.assertIsNone(analytics["benchmark_metrics"])

        status, queue = self.request(
            "GET", f"/network/datasets/{dataset_id}/incidents"
        )
        self.assertEqual(status, 200, queue)
        self.assertEqual(queue["total"], 1)
        compact = queue["items"][0]
        self.assertIsNone(compact["actual_label"])
        self.assertIsNone(compact["actual_family"])

        status, detail = self.request(
            "GET", f"/network/incidents/{compact['incident_id']}"
        )
        self.assertEqual(status, 200, detail)
        self.assertIsNone(detail["prediction"]["actual_binary"])
        self.assertIsNone(detail["prediction"]["is_correct"])
        self.assertIsNone(detail["flow_context"]["actual_label"])
        self.assertIsNone(detail["flow_context"]["actual_family"])
        self.assertIsNone(detail["flow_context"]["difficulty_level"])


if __name__ == "__main__":
    unittest.main()
