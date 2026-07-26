"""Focused API and transaction tests for network dataset ingestion."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlencode

from fastapi import FastAPI
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.auth.service import get_current_user
from backend.app.database import models  # noqa: F401 - registers all tables
from backend.app.database.network_models import NetworkDataset, NetworkFlow
from backend.app.database.session import Base, get_db
from backend.app.network import routes as network_routes
from backend.app.network import service as network_service
from backend.app.network.routes import router
from ml_pipeline.nsl_kdd_schema import (
    ALL_COLUMNS,
    CATEGORICAL_COLUMNS,
    FEATURE_COLUMNS,
)


def feature_record(seed: int = 0) -> dict:
    """Create one small valid record from the official feature constants."""
    record = {}
    for column in FEATURE_COLUMNS:
        if column == "protocol_type":
            record[column] = "tcp" if seed % 2 == 0 else "udp"
        elif column == "service":
            record[column] = "http" if seed % 2 == 0 else "domain_u"
        elif column == "flag":
            record[column] = "SF" if seed % 2 == 0 else "S0"
        elif column.endswith("_rate"):
            record[column] = 0.0
        else:
            record[column] = 0
    record["duration"] = seed
    record["src_bytes"] = 100 + seed
    record["dst_bytes"] = 200 + seed
    record["count"] = 10 + seed
    record["srv_count"] = 5 + seed
    return record


def dataset_bytes(
    labelled: bool,
    headered: bool,
    rows: list[dict] | None = None,
    reverse_header: bool = False,
) -> bytes:
    """Serialize small official-schema fixtures as comma-separated UTF-8."""
    if rows is None:
        rows = [feature_record(1), feature_record(2)]
        if labelled:
            rows[0].update({"label": " normal. ", "difficulty_level": 21})
            rows[1].update({"label": "Back.", "difficulty_level": 18})
    columns = list(ALL_COLUMNS if labelled else FEATURE_COLUMNS)
    if headered and reverse_header:
        columns.reverse()
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    if headered:
        writer.writerow(columns)
    for row in rows:
        writer.writerow([row[column] for column in columns])
    return output.getvalue().encode("utf-8")


def multipart_body(filename: str, content: bytes) -> tuple[bytes, str]:
    """Build a single-file multipart body without an HTTP client dependency."""
    boundary = "athes-network-test-boundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: text/plain\r\n\r\n"
    ).encode("utf-8")
    body += content
    body += f"\r\n--{boundary}--\r\n".encode("utf-8")
    return body, f"multipart/form-data; boundary={boundary}"


async def asgi_request(
    app: FastAPI,
    method: str,
    path: str,
    *,
    body: bytes = b"",
    headers: dict[str, str] | None = None,
    query: dict[str, int] | None = None,
) -> tuple[int, dict]:
    """Issue one HTTP request directly through ASGI."""
    request_headers = {
        "host": "testserver",
        "content-length": str(len(body)),
        **(headers or {}),
    }
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method.upper(),
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": urlencode(query or {}).encode("ascii"),
        "headers": [
            (name.lower().encode("latin-1"), value.encode("latin-1"))
            for name, value in request_headers.items()
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    messages: list[dict] = []
    delivered = False

    async def receive() -> dict:
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: dict) -> None:
        messages.append(message)

    await app(scope, receive, send)
    start = next(message for message in messages if message["type"] == "http.response.start")
    response_body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return start["status"], json.loads(response_body or b"{}")


class NetworkIngestionApiTest(unittest.TestCase):
    """Verify authenticated upload, persistence, validation, and reading."""

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

    def authenticate(self, role: str = "admin") -> None:
        user = SimpleNamespace(id=1, username=f"{role}-user", role=role)
        self.app.dependency_overrides[get_current_user] = lambda: user

    def request(
        self,
        method: str,
        path: str,
        *,
        content: bytes = b"",
        filename: str = "network.txt",
        query: dict[str, int] | None = None,
    ) -> tuple[int, dict]:
        headers = None
        body = b""
        if method.upper() == "POST":
            body, content_type = multipart_body(filename, content)
            headers = {"content-type": content_type}
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

    def upload(
        self,
        content: bytes,
        filename: str = "network.txt",
    ) -> tuple[int, dict]:
        return self.request(
            "POST",
            "/network/datasets/upload",
            content=content,
            filename=filename,
        )

    def test_all_endpoints_require_existing_authentication(self):
        upload_status, _ = self.upload(dataset_bytes(True, False))
        list_status, _ = self.request("GET", "/network/datasets")
        detail_status, _ = self.request("GET", "/network/datasets/1")
        flows_status, _ = self.request(
            "GET", "/network/datasets/1/flows"
        )
        self.assertEqual(upload_status, 401)
        self.assertEqual(list_status, 401)
        self.assertEqual(detail_status, 401)
        self.assertEqual(flows_status, 401)

    def test_headerless_labelled_upload_and_duplicate_filename(self):
        self.authenticate("admin")
        status, response = self.upload(
            dataset_bytes(True, False), filename="KDDTest+.txt"
        )
        self.assertEqual(status, 201, response)
        self.assertTrue(response["has_ground_truth"])
        self.assertEqual(response["source_type"], "nsl_kdd_labelled")
        self.assertEqual(response["analysis_status"], "uploaded")
        self.assertEqual(response["total_records"], 2)
        self.assertEqual(
            {item["value"]: item["count"] for item in response["label_distribution"]},
            {"normal": 1, "back": 1},
        )
        self.assertEqual(
            {
                item["value"]: item["count"]
                for item in response["attack_family_distribution"]
            },
            {"normal": 1, "dos": 1},
        )
        self.assertEqual(response["service_unique_count"], 2)

        with self.Session() as session:
            flows = (
                session.query(NetworkFlow)
                .filter(NetworkFlow.dataset_id == response["id"])
                .order_by(NetworkFlow.row_number)
                .all()
            )
            self.assertEqual([flow.row_number for flow in flows], [1, 2])
            self.assertEqual([flow.duration for flow in flows], [1, 2])
            self.assertEqual([flow.actual_label for flow in flows], ["normal", "back"])
            self.assertEqual([flow.actual_family for flow in flows], ["normal", "dos"])
            self.assertEqual([flow.difficulty_level for flow in flows], [21, 18])

        self.authenticate("analyst")
        second_status, second = self.upload(
            dataset_bytes(True, False), filename="KDDTest+.txt"
        )
        self.assertEqual(second_status, 201, second)
        self.assertNotEqual(response["id"], second["id"])
        with self.Session() as session:
            self.assertEqual(session.query(NetworkDataset).count(), 2)
        self.assertNotIn(
            "backend.app.ml.nsl_kdd_inference",
            sys.modules,
            "Upload unexpectedly imported the inference module.",
        )

    def test_headerless_inference_upload_has_null_benchmark_fields(self):
        self.authenticate("analyst")
        status, response = self.upload(
            dataset_bytes(False, False), filename="flows.csv"
        )
        self.assertEqual(status, 201, response)
        self.assertFalse(response["has_ground_truth"])
        self.assertEqual(response["source_type"], "nsl_kdd_inference")
        self.assertEqual(response["label_distribution"], [])
        self.assertEqual(response["attack_family_distribution"], [])
        with self.Session() as session:
            flows = session.query(NetworkFlow).order_by(NetworkFlow.row_number).all()
            self.assertEqual([flow.row_number for flow in flows], [1, 2])
            self.assertTrue(all(flow.actual_label is None for flow in flows))
            self.assertTrue(all(flow.actual_family is None for flow in flows))
            self.assertTrue(all(flow.difficulty_level is None for flow in flows))

    def test_headered_labelled_and_inference_uploads_allow_reordering(self):
        self.authenticate()
        labelled_status, labelled = self.upload(
            dataset_bytes(True, True, reverse_header=True),
            filename="labelled.csv",
        )
        inference_status, inference = self.upload(
            dataset_bytes(False, True, reverse_header=True),
            filename="inference.csv",
        )
        self.assertEqual(labelled_status, 201, labelled)
        self.assertEqual(inference_status, 201, inference)
        self.assertTrue(labelled["has_ground_truth"])
        self.assertFalse(inference["has_ground_truth"])
        self.assertEqual(labelled["total_records"], 2)
        self.assertEqual(inference["total_records"], 2)

    def test_validation_failures(self):
        self.authenticate()
        valid_record = feature_record(1)
        labelled_record = {
            **valid_record,
            "label": "normal",
            "difficulty_level": 21,
        }

        invalid_numeric = dict(valid_record)
        invalid_numeric["duration"] = "not-numeric"
        missing_value = dict(valid_record)
        missing_value["duration"] = ""
        infinite_value = dict(valid_record)
        infinite_value["duration"] = "inf"
        invalid_difficulty = dict(labelled_record)
        invalid_difficulty["difficulty_level"] = 1.5
        unmapped_label = dict(labelled_record)
        unmapped_label["label"] = "unknown_attack"

        duplicate_header = list(FEATURE_COLUMNS)
        duplicate_header[1] = duplicate_header[0]
        missing_header = list(FEATURE_COLUMNS[:-1])
        extra_header = [*FEATURE_COLUMNS, "unsupported_extra"]

        def header_content(columns: list[str], record: dict) -> bytes:
            output = io.StringIO(newline="")
            writer = csv.writer(output, lineterminator="\n")
            writer.writerow(columns)
            writer.writerow([record.get(column, 0) for column in columns])
            return output.getvalue().encode()

        cases = [
            ("unsupported.exe", dataset_bytes(False, False), 400, "extension"),
            ("empty.csv", b"", 400, "empty"),
            ("wrong.csv", b",".join([b"0"] * 40), 400, "41 or 43"),
            ("partial.csv", b",".join([b"0"] * 42), 400, "41 or 43"),
            (
                "duplicate.csv",
                header_content(duplicate_header, valid_record),
                400,
                "duplicate",
            ),
            (
                "missing.csv",
                header_content(missing_header, valid_record),
                400,
                "missing",
            ),
            (
                "extra.csv",
                header_content(extra_header, valid_record),
                400,
                "unsupported extra",
            ),
            (
                "numeric.csv",
                dataset_bytes(False, False, rows=[invalid_numeric]),
                400,
                "duration",
            ),
            (
                "missing-value.csv",
                dataset_bytes(False, False, rows=[missing_value]),
                400,
                "missing",
            ),
            (
                "infinity.csv",
                dataset_bytes(False, False, rows=[infinite_value]),
                400,
                "infinity",
            ),
            (
                "difficulty.csv",
                dataset_bytes(True, False, rows=[invalid_difficulty]),
                400,
                "difficulty",
            ),
            (
                "label.csv",
                dataset_bytes(True, False, rows=[unmapped_label]),
                400,
                "unmapped",
            ),
            ("decode.csv", b"\xff\xfe\xfa", 400, "utf-8"),
        ]
        for filename, content, expected_status, detail_text in cases:
            with self.subTest(filename=filename):
                status, response = self.upload(content, filename=filename)
                self.assertEqual(status, expected_status, response)
                self.assertIn(detail_text, response["detail"].lower())

        with (
            patch.object(network_routes, "MAX_UPLOAD_BYTES", 10),
            patch.object(network_service, "MAX_UPLOAD_BYTES", 10),
        ):
            status, response = self.upload(b"x" * 11, filename="large.csv")
        self.assertEqual(status, 413, response)
        self.assertIn("limit", response["detail"].lower())
        with self.Session() as session:
            self.assertEqual(session.query(NetworkDataset).count(), 0)
            self.assertEqual(session.query(NetworkFlow).count(), 0)

    def test_persistence_failure_rolls_back_parent_and_inserted_batch(self):
        self.authenticate()
        original_execute = network_service._execute_flow_batch
        calls = 0

        def fail_second_batch(db, rows):
            nonlocal calls
            calls += 1
            if calls == 1:
                original_execute(db, rows)
                return
            raise RuntimeError("forced insertion failure")

        with (
            patch.object(network_service, "FLOW_INSERT_BATCH_SIZE", 1),
            patch.object(
                network_service,
                "_execute_flow_batch",
                side_effect=fail_second_batch,
            ),
        ):
            status, response = self.upload(dataset_bytes(True, False))
        self.assertEqual(status, 500, response)
        self.assertIn("no records were committed", response["detail"].lower())
        with self.Session() as session:
            self.assertEqual(session.query(NetworkDataset).count(), 0)
            self.assertEqual(session.query(NetworkFlow).count(), 0)

    def test_read_endpoints_order_counts_and_pagination(self):
        self.authenticate()
        rows = [feature_record(3), feature_record(1), feature_record(2)]
        first_status, first = self.upload(
            dataset_bytes(False, False, rows=rows),
            filename="first.csv",
        )
        second_status, second = self.upload(
            dataset_bytes(False, False, rows=[feature_record(9)]),
            filename="second.csv",
        )
        self.assertEqual(first_status, 201, first)
        self.assertEqual(second_status, 201, second)

        list_status, first_page = self.request(
            "GET", "/network/datasets", query={"limit": 1, "offset": 0}
        )
        _, second_page = self.request(
            "GET", "/network/datasets", query={"limit": 1, "offset": 1}
        )
        self.assertEqual(list_status, 200, first_page)
        self.assertEqual(first_page["total"], 2)
        self.assertEqual(first_page["items"][0]["id"], second["id"])
        self.assertEqual(second_page["items"][0]["id"], first["id"])

        detail_status, detail = self.request(
            "GET", f"/network/datasets/{first['id']}"
        )
        self.assertEqual(detail_status, 200, detail)
        self.assertEqual(detail["stored_flow_count"], 3)
        self.assertEqual(detail["prediction_count"], 0)
        self.assertEqual(detail["incident_count"], 0)
        self.assertEqual(detail["predicted_normal_count"], 0)
        self.assertEqual(detail["predicted_attack_count"], 0)

        flow_status, flow_page = self.request(
            "GET",
            f"/network/datasets/{first['id']}/flows",
            query={"limit": 1, "offset": 1},
        )
        self.assertEqual(flow_status, 200, flow_page)
        self.assertEqual(flow_page["total"], 3)
        self.assertEqual(flow_page["items"][0]["row_number"], 2)
        self.assertEqual(flow_page["items"][0]["duration"], 1)
        self.assertEqual(set(CATEGORICAL_COLUMNS) <= set(flow_page["items"][0]), True)

        unknown_detail, _ = self.request("GET", "/network/datasets/99999")
        unknown_flows, _ = self.request(
            "GET", "/network/datasets/99999/flows"
        )
        self.assertEqual(unknown_detail, 404)
        self.assertEqual(unknown_flows, 404)

        list_max, _ = self.request(
            "GET", "/network/datasets", query={"limit": 201}
        )
        flow_max, _ = self.request(
            "GET",
            f"/network/datasets/{first['id']}/flows",
            query={"limit": 501},
        )
        self.assertEqual(list_max, 422)
        self.assertEqual(flow_max, 422)


if __name__ == "__main__":
    unittest.main()
