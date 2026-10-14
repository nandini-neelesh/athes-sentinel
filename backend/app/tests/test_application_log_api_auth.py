"""Regression tests for authentication on the application-log API.

These tests were added during the September 2026 repair pass. They lock in two
behaviours that the application-log routes did not previously have:

1. Every application-log endpoint rejects an unauthenticated caller with 401.
2. A successful upload records which user performed it in the log_files table.

They follow the same conventions as the network test modules: an isolated
in-memory SQLite database, a private FastAPI instance, and requests issued
straight through ASGI so no extra HTTP client dependency is required.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import unittest
from types import SimpleNamespace
from urllib.parse import urlencode

from fastapi import FastAPI
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.analytics.routes import router as analytics_router
from backend.app.auth.service import get_current_user
from backend.app.database import models  # noqa: F401 - registers all tables
from backend.app.database.models import LogFile
from backend.app.database.session import Base, get_db
from backend.app.detection.routes import router as ml_router
from backend.app.features.routes import router as features_router
from backend.app.incidents.routes import router as incidents_router
from backend.app.logs.routes import router as logs_router


LOG_COLUMNS = [
    "timestamp",
    "ip_address",
    "user_id",
    "endpoint",
    "method",
    "status_code",
    "response_time_ms",
    "event_type",
    "user_agent",
]


def log_csv_bytes(rows: int = 6) -> bytes:
    """Build a small valid application-log CSV in the documented format."""
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(LOG_COLUMNS)
    for index in range(rows):
        writer.writerow(
            [
                f"2026-06-12 10:{index:02d}:00",
                "192.168.1.10",
                f"u{index:03d}",
                "/login",
                "POST",
                401 if index % 2 else 200,
                100.0 + index,
                "login_failed" if index % 2 else "login_success",
                "Mozilla/5.0",
            ]
        )
    return output.getvalue().encode("utf-8")


def multipart_body(filename: str, content: bytes) -> tuple[bytes, str]:
    """Build a single-file multipart body without an HTTP client dependency."""
    boundary = "athes-applog-test-boundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: text/csv\r\n\r\n"
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
    query: dict[str, object] | None = None,
) -> tuple[int, object]:
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
    start = next(
        message for message in messages if message["type"] == "http.response.start"
    )
    response_body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return start["status"], json.loads(response_body or b"{}")


class ApplicationLogAuthTest(unittest.TestCase):
    """Verify application-log routes are authenticated and attribute uploads."""

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
        for router in (
            analytics_router,
            features_router,
            incidents_router,
            logs_router,
            ml_router,
        ):
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

    def authenticate(self, user_id: int = 7, role: str = "analyst") -> None:
        user = SimpleNamespace(id=user_id, username=f"{role}-user", role=role)
        self.app.dependency_overrides[get_current_user] = lambda: user

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes = b"",
        headers: dict[str, str] | None = None,
        query: dict[str, object] | None = None,
    ) -> tuple[int, object]:
        return asyncio.run(
            asgi_request(
                self.app, method, path, body=body, headers=headers, query=query
            )
        )

    def upload(self, content: bytes, filename: str = "logs.csv"):
        body, content_type = multipart_body(filename, content)
        return self.request(
            "POST",
            "/logs/upload",
            body=body,
            headers={"content-type": content_type},
        )

    def test_every_application_log_endpoint_rejects_anonymous_callers(self):
        """Without a bearer token, all 18 application-log routes return 401."""
        get_paths = [
            "/logs",
            "/logs/files",
            "/features/1",
            "/ml/scores/1",
            "/incidents",
            "/incidents/1",
            "/analytics/summary/1",
            "/analytics/status-codes/1",
            "/analytics/top-ips/1",
            "/analytics/hourly-traffic/1",
            "/analytics/top-endpoints/1",
            "/analytics/slowest-endpoints/1",
            "/analytics/error-rate-by-endpoint/1",
        ]
        post_paths = [
            "/features/generate/1",
            "/ml/run/1",
            "/incidents/generate/1",
        ]

        for path in get_paths:
            with self.subTest(method="GET", path=path):
                status, payload = self.request("GET", path)
                self.assertEqual(status, 401)
                self.assertEqual(payload, {"detail": "Not authenticated"})

        for path in post_paths:
            with self.subTest(method="POST", path=path):
                status, payload = self.request("POST", path)
                self.assertEqual(status, 401)
                self.assertEqual(payload, {"detail": "Not authenticated"})

        upload_status, upload_payload = self.upload(log_csv_bytes())
        self.assertEqual(upload_status, 401)
        self.assertEqual(upload_payload, {"detail": "Not authenticated"})

        patch_status, patch_payload = self.request(
            "PATCH",
            "/incidents/1/status",
            body=json.dumps({"status": "resolved"}).encode("utf-8"),
            headers={"content-type": "application/json"},
        )
        self.assertEqual(patch_status, 401)
        self.assertEqual(patch_payload, {"detail": "Not authenticated"})

        # Nothing reached the database while every call was rejected.
        session = self.Session()
        try:
            self.assertEqual(session.query(LogFile).count(), 0)
        finally:
            session.close()

    def test_rejected_upload_is_accepted_once_authenticated(self):
        """The same upload that fails anonymously succeeds with a token."""
        anonymous_status, _ = self.upload(log_csv_bytes(rows=4))
        self.assertEqual(anonymous_status, 401)

        self.authenticate(user_id=7)
        status, payload = self.upload(log_csv_bytes(rows=4))

        self.assertEqual(status, 200)
        self.assertEqual(payload["filename"], "logs.csv")
        self.assertEqual(payload["rows_inserted"], 4)

    def test_upload_records_the_authenticated_uploader(self):
        """The uploaded_by column stores the signed-in user's id, not null."""
        self.authenticate(user_id=42)
        status, payload = self.upload(log_csv_bytes(rows=3), filename="first.csv")
        self.assertEqual(status, 200)
        first_file_id = payload["file_id"]

        self.authenticate(user_id=99, role="admin")
        status, payload = self.upload(log_csv_bytes(rows=3), filename="second.csv")
        self.assertEqual(status, 200)
        second_file_id = payload["file_id"]

        session = self.Session()
        try:
            first = session.get(LogFile, first_file_id)
            second = session.get(LogFile, second_file_id)
            self.assertEqual(first.uploaded_by, 42)
            self.assertEqual(second.uploaded_by, 99)
        finally:
            session.close()

        listing_status, listing = self.request("GET", "/logs/files")
        self.assertEqual(listing_status, 200)
        uploaders = {row["filename"]: row["uploaded_by"] for row in listing}
        self.assertEqual(uploaders, {"first.csv": 42, "second.csv": 99})

    def test_invalid_upload_still_returns_400_for_an_authenticated_caller(self):
        """Authentication runs first, but validation errors are unchanged."""
        self.authenticate()
        body, content_type = multipart_body("bad.csv", b"not,a,log\n1,2,3\n")
        status, payload = self.request(
            "POST",
            "/logs/upload",
            body=body,
            headers={"content-type": content_type},
        )

        self.assertEqual(status, 400)
        self.assertIn("Missing required CSV columns", payload["detail"])

        session = self.Session()
        try:
            self.assertEqual(session.query(LogFile).count(), 0)
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
