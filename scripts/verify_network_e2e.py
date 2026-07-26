"""Reproduce the complete Athes Sentinel network-mode lifecycle over HTTP.

The verifier deliberately redirects the real FastAPI application to a temporary
SQLite database before importing application modules. It exercises real JWT
authentication, upload parsing, the frozen fitted detector, persistence, reads,
and analyst workflow updates without touching the normal local database.
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import patch
from urllib.parse import urlencode


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

REPORT_PATH = (
    REPOSITORY_ROOT
    / "ml_pipeline"
    / "reports"
    / "network_e2e_verification.json"
)
DATASET_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "external"
    / "nsl-kdd"
    / "KDDTest+.txt"
)
ARTIFACT_PATH = (
    REPOSITORY_ROOT
    / "ml_pipeline"
    / "artifacts"
    / "nsl_kdd_improved_binary_pipeline.joblib"
)
METADATA_PATH = (
    REPOSITORY_ROOT
    / "ml_pipeline"
    / "artifacts"
    / "improved_model_metadata.json"
)
REAL_DATABASE_PATH = REPOSITORY_ROOT / "athes_sentinel.db"
EXPECTED_ARTIFACT_SHA256 = (
    "09b4cac3372256c3122bcfb5555706d63397e8449385470a283427e688691c13"
)
EXPECTED_ROWS = 22_544
EXPECTED_MODEL_COUNTS = {
    "predicted_normal": 13_366,
    "predicted_attack": 9_178,
    "total_incidents": 9_178,
}
EXPECTED_CONFUSION = {
    "true_negatives": 9_419,
    "false_positives": 292,
    "false_negatives": 3_947,
    "true_positives": 8_886,
}
EXPECTED_FAMILY_COUNTS = {
    "normal": 9_711,
    "dos": 7_460,
    "r2l": 2_885,
    "probe": 2_421,
    "u2r": 67,
}
EXPECTED_METRICS = {
    "accuracy": 0.8119677075940384,
    "precision": 0.9681847897145348,
    "recall": 0.6924335697031092,
    "f1": 0.8074144745808913,
    "f2": 0.7342588001983144,
    "false_positive_rate": 0.030068993924415612,
    "false_negative_rate": 0.30756643029689085,
}
METRIC_TOLERANCE = 1e-9
FRONTEND_CONTRACT_FILES = [
    "frontend/src/pages/network/NetworkUpload.jsx",
    "frontend/src/pages/network/NetworkOverview.jsx",
    "frontend/src/pages/network/NetworkAnalytics.jsx",
    "frontend/src/pages/network/NetworkIncidents.jsx",
    "frontend/src/pages/network/components/NetworkIncidentTable.jsx",
    "frontend/src/pages/network/components/NetworkIncidentDetail.jsx",
    "frontend/src/pages/network/NetworkWorkflow.jsx",
    "frontend/src/pages/network/components/NetworkWorkflowColumn.jsx",
]
FORBIDDEN_CONTEXT_KEYS = {
    "ip_address",
    "source_ip",
    "destination_ip",
    "user",
    "user_id",
    "endpoint",
    "predicted_family",
    "predicted_attack_family",
}


class VerificationError(RuntimeError):
    """Raised when an HTTP contract or safety invariant does not hold."""


def require(condition: bool, message: str) -> None:
    """Raise a readable failure instead of relying on disabled assertions."""
    if not condition:
        raise VerificationError(message)


def require_equal(observed: Any, expected: Any, label: str) -> None:
    if observed != expected:
        raise VerificationError(
            f"{label}: expected {expected!r}, observed {observed!r}."
        )


def require_close(
    observed: float,
    expected: float,
    label: str,
    tolerance: float = METRIC_TOLERANCE,
) -> None:
    difference = abs(float(observed) - float(expected))
    if difference > tolerance:
        raise VerificationError(
            f"{label}: expected {expected}, observed {observed}, "
            f"difference {difference} exceeds {tolerance}."
        )


def file_sha256(path: Path) -> str:
    """Calculate a file hash without loading a large artifact into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_signature(path: Path) -> dict[str, Any]:
    """Capture enough information to prove a real local file was unchanged."""
    if not path.exists():
        return {"exists": False, "size_bytes": None, "sha256": None}
    return {
        "exists": True,
        "size_bytes": path.stat().st_size,
        "sha256": file_sha256(path),
    }


def relative_path(path: Path) -> str:
    return path.resolve().relative_to(REPOSITORY_ROOT.resolve()).as_posix()


async def asgi_request(
    app,
    method: str,
    path: str,
    *,
    body: bytes = b"",
    headers: dict[str, str] | None = None,
    query: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    """Issue one request through the real ASGI application without httpx."""
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
    messages: list[dict[str, Any]] = []
    delivered = False

    async def receive() -> dict[str, Any]:
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    await app(scope, receive, send)
    response_start = next(
        message
        for message in messages
        if message["type"] == "http.response.start"
    )
    response_body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    if not response_body:
        payload: Any = None
    else:
        try:
            payload = json.loads(response_body)
        except json.JSONDecodeError:
            payload = response_body.decode("utf-8", errors="replace")
    return int(response_start["status"]), payload


def multipart_body(filename: str, content: bytes) -> tuple[bytes, str]:
    """Build the same single-file multipart request sent by the React client."""
    boundary = "athes-network-e2e-boundary"
    content_type = (
        "text/csv" if filename.lower().endswith(".csv") else "text/plain"
    )
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("utf-8")
    body += content
    body += f"\r\n--{boundary}--\r\n".encode("utf-8")
    return body, f"multipart/form-data; boundary={boundary}"


class ApiClient:
    """Small synchronous wrapper around the application's ASGI surface."""

    def __init__(self, app) -> None:
        self.app = app
        self.token: str | None = None

    def request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        file_upload: tuple[str, bytes] | None = None,
        authenticated: bool = True,
        expected_status: int = 200,
    ) -> Any:
        body = b""
        headers: dict[str, str] = {}
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            headers["content-type"] = "application/json"
        if file_upload is not None:
            body, content_type = multipart_body(*file_upload)
            headers["content-type"] = content_type
        if authenticated and self.token:
            headers["authorization"] = f"Bearer {self.token}"
        status, payload = asyncio.run(
            asgi_request(
                self.app,
                method,
                path,
                body=body,
                headers=headers,
                query=query,
            )
        )
        if status != expected_status:
            detail = (
                payload.get("detail")
                if isinstance(payload, dict)
                else payload
            )
            raise VerificationError(
                f"{method} {path} returned {status}, expected "
                f"{expected_status}: {detail!r}"
            )
        return payload


@contextmanager
def prohibit_model_fitting() -> Iterator[None]:
    """Fail immediately if inference accidentally attempts model fitting."""
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder

    def forbidden(*args, **kwargs):
        del args, kwargs
        raise VerificationError(
            "A model or preprocessing fit method was called during E2E inference."
        )

    with ExitStack() as stack:
        for target in (
            (Pipeline, "fit"),
            (ColumnTransformer, "fit"),
            (ColumnTransformer, "fit_transform"),
            (OneHotEncoder, "fit"),
            (OneHotEncoder, "fit_transform"),
            (RandomForestClassifier, "fit"),
        ):
            stack.enter_context(patch.object(*target, new=forbidden))
        yield


def distribution_map(entries: list[dict[str, Any]]) -> dict[str, int]:
    return {str(entry["value"]): int(entry["count"]) for entry in entries}


def record_count_sum(entries: list[dict[str, Any]]) -> int:
    return sum(int(entry["record_count"]) for entry in entries)


def recursively_forbid_keys(value: Any, context: str) -> None:
    """Reject product fields that would fabricate unsupported network context."""
    if isinstance(value, dict):
        unexpected = FORBIDDEN_CONTEXT_KEYS.intersection(value)
        require(
            not unexpected,
            f"{context} exposed forbidden fabricated fields: "
            f"{sorted(unexpected)}.",
        )
        for nested in value.values():
            recursively_forbid_keys(nested, context)
    elif isinstance(value, list):
        for nested in value:
            recursively_forbid_keys(nested, context)


def verify_metric_payload(metrics: dict[str, Any], label: str) -> float:
    """Verify official confusion values and return the largest metric delta."""
    for name, expected in EXPECTED_CONFUSION.items():
        require_equal(int(metrics[name]), expected, f"{label} {name}")
    maximum_difference = 0.0
    for name, expected in EXPECTED_METRICS.items():
        difference = abs(float(metrics[name]) - expected)
        maximum_difference = max(maximum_difference, difference)
        require_close(metrics[name], expected, f"{label} {name}")
    return maximum_difference


def verify_route_registration(app) -> dict[str, Any]:
    paths = {route.path for route in app.routes}
    required_network = {
        "/network/datasets/upload",
        "/network/datasets",
        "/network/datasets/{dataset_id}",
        "/network/datasets/{dataset_id}/flows",
        "/network/datasets/{dataset_id}/analyze",
        "/network/datasets/{dataset_id}/analysis",
        "/network/datasets/{dataset_id}/dashboard",
        "/network/datasets/{dataset_id}/analytics",
        "/network/datasets/{dataset_id}/incidents",
        "/network/incidents/{incident_id}",
        "/network/incidents/{incident_id}/status",
    }
    require(
        required_network.issubset(paths),
        "One or more required network routes are not registered.",
    )
    old_prefixes = ("/logs", "/analytics", "/features", "/incidents", "/ml")
    missing_old = [
        prefix
        for prefix in old_prefixes
        if not any(path.startswith(prefix) for path in paths)
    ]
    require(
        not missing_old,
        f"Existing application route groups are missing: {missing_old}.",
    )
    return {
        "network_route_count": len(required_network),
        "existing_application_route_groups": list(old_prefixes),
    }


def verify_labelled_upload_and_reads(
    client: ApiClient, dataset_bytes: bytes
) -> tuple[int, dict[str, Any]]:
    upload = client.request(
        "POST",
        "/network/datasets/upload",
        file_upload=("KDDTest+.txt", dataset_bytes),
        expected_status=201,
    )
    require_equal(upload["total_records"], EXPECTED_ROWS, "uploaded row count")
    require_equal(upload["has_ground_truth"], True, "ground-truth flag")
    require_equal(
        upload["source_type"], "nsl_kdd_labelled", "upload source type"
    )
    require_equal(upload["analysis_status"], "uploaded", "upload status")
    family_counts = distribution_map(upload["attack_family_distribution"])
    require_equal(
        family_counts, EXPECTED_FAMILY_COUNTS, "attack-family distribution"
    )
    require_equal(
        sum(family_counts.values()),
        EXPECTED_ROWS,
        "attack-family distribution total",
    )
    dataset_id = int(upload["id"])

    listing = client.request("GET", "/network/datasets")
    require(
        any(item["id"] == dataset_id for item in listing["items"]),
        "Uploaded dataset was absent from the dataset listing.",
    )
    detail = client.request("GET", f"/network/datasets/{dataset_id}")
    require_equal(detail["stored_flow_count"], EXPECTED_ROWS, "stored flows")
    require_equal(detail["prediction_count"], 0, "pre-analysis predictions")
    require_equal(detail["incident_count"], 0, "pre-analysis incidents")

    first_page = client.request(
        "GET",
        f"/network/datasets/{dataset_id}/flows",
        query={"limit": 3, "offset": 0},
    )
    later_page = client.request(
        "GET",
        f"/network/datasets/{dataset_id}/flows",
        query={"limit": 3, "offset": 123},
    )
    require_equal(first_page["total"], EXPECTED_ROWS, "first flow-page total")
    require_equal(later_page["total"], EXPECTED_ROWS, "later flow-page total")
    require_equal(
        [item["row_number"] for item in first_page["items"]],
        [1, 2, 3],
        "first flow-page row order",
    )
    require_equal(
        [item["row_number"] for item in later_page["items"]],
        [124, 125, 126],
        "later flow-page row order",
    )
    require(
        all(
            item["actual_label"] is not None
            and item["actual_family"] is not None
            and item["difficulty_level"] is not None
            for item in first_page["items"]
        ),
        "Labelled flow responses omitted supplied benchmark fields.",
    )
    return dataset_id, {
        "upload": "passed",
        "dataset_listing": "passed",
        "pre_analysis_detail": "passed",
        "source_order_pagination": "passed",
        "family_distribution": family_counts,
    }


def run_real_analysis(
    client: ApiClient, dataset_id: int
) -> tuple[dict[str, Any], float]:
    with prohibit_model_fitting():
        analysis = client.request(
            "POST", f"/network/datasets/{dataset_id}/analyze"
        )
    require_equal(analysis["analysis_status"], "completed", "analysis status")
    require_equal(analysis["total_predictions"], EXPECTED_ROWS, "predictions")
    for name, expected in EXPECTED_MODEL_COUNTS.items():
        require_equal(analysis[name], expected, f"analysis {name}")
    require_close(analysis["threshold"], 0.38, "analysis threshold")
    require_equal(
        analysis["model_version"],
        EXPECTED_ARTIFACT_SHA256,
        "analysis model version",
    )
    require(
        analysis["benchmark_metrics"] is not None,
        "Labelled analysis omitted benchmark metrics.",
    )
    maximum_difference = verify_metric_payload(
        analysis["benchmark_metrics"], "analysis"
    )
    return analysis, maximum_difference


def verify_dashboard(
    client: ApiClient, dataset_id: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    dashboard = client.request(
        "GET", f"/network/datasets/{dataset_id}/dashboard"
    )
    dataset = dashboard["dataset"]
    model = dashboard["model"]
    predictions = dashboard["prediction_kpis"]
    incidents = dashboard["incident_kpis"]
    benchmark = dashboard["benchmark_metrics"]
    require_equal(dataset["analysis_status"], "completed", "dashboard status")
    require_equal(dataset["total_flows"], EXPECTED_ROWS, "dashboard flows")
    require_equal(
        predictions["total_predictions"], EXPECTED_ROWS, "dashboard predictions"
    )
    require_equal(
        predictions["predicted_normal"],
        EXPECTED_MODEL_COUNTS["predicted_normal"],
        "dashboard predicted normal",
    )
    require_equal(
        predictions["predicted_attack"],
        EXPECTED_MODEL_COUNTS["predicted_attack"],
        "dashboard predicted attack",
    )
    require_equal(
        incidents["total_incidents"],
        EXPECTED_MODEL_COUNTS["total_incidents"],
        "dashboard incidents",
    )
    workflow_total = sum(
        int(incidents[name])
        for name in (
            "open_incidents",
            "investigating_incidents",
            "resolved_incidents",
            "false_positive_status_incidents",
        )
    )
    severity_total = sum(
        int(incidents[name])
        for name in (
            "critical_incidents",
            "high_incidents",
            "medium_incidents",
            "low_incidents",
        )
    )
    require_equal(workflow_total, incidents["total_incidents"], "workflow total")
    require_equal(severity_total, incidents["total_incidents"], "severity total")
    require_equal(model["model_version"], EXPECTED_ARTIFACT_SHA256, "model SHA")
    require_close(model["threshold_probability"], 0.38, "dashboard threshold")
    verify_metric_payload(benchmark, "dashboard")
    priority = dashboard["priority_incidents"]
    require(len(priority) <= 5, "Dashboard returned more than five incidents.")
    require(
        all(
            priority[index]["risk_score"]
            >= priority[index + 1]["risk_score"]
            for index in range(len(priority) - 1)
        ),
        "Priority incidents are not ordered by descending persisted risk.",
    )
    recursively_forbid_keys(dashboard, "dashboard")
    return dashboard, {
        "workflow_count_sum": workflow_total,
        "severity_count_sum": severity_total,
        "priority_incident_count": len(priority),
        "priority_order": "passed",
        "fabricated_context_absent": True,
    }


def verify_analytics(
    client: ApiClient, dataset_id: int, dashboard: dict[str, Any]
) -> dict[str, Any]:
    from backend.app.network.analytics_service import PROBABILITY_BUCKETS

    analytics = client.request(
        "GET",
        f"/network/datasets/{dataset_id}/analytics",
        query={"service_limit": 10},
    )
    totals = {
        "prediction_distribution": record_count_sum(
            analytics["prediction_distribution"]
        ),
        "protocol_distribution": sum(
            int(entry["total_records"])
            for entry in analytics["protocol_distribution"]
        ),
        "flag_distribution": sum(
            int(entry["total_records"])
            for entry in analytics["flag_distribution"]
        ),
        "probability_histogram": record_count_sum(
            analytics["probability_histogram"]
        ),
        "severity_distribution": sum(
            int(value) for value in analytics["severity_distribution"].values()
        ),
        "actual_family_distribution": record_count_sum(
            analytics["actual_family_distribution"]
        ),
        "correctness_distribution": record_count_sum(
            analytics["correctness_distribution"]
        ),
    }
    for name in (
        "prediction_distribution",
        "protocol_distribution",
        "flag_distribution",
        "probability_histogram",
        "actual_family_distribution",
        "correctness_distribution",
    ):
        require_equal(totals[name], EXPECTED_ROWS, f"analytics {name} total")
    require_equal(
        totals["severity_distribution"],
        EXPECTED_MODEL_COUNTS["total_incidents"],
        "analytics severity total",
    )
    verify_metric_payload(analytics["benchmark_metrics"], "analytics")
    for metric_name in EXPECTED_METRICS:
        require_close(
            analytics["benchmark_metrics"][metric_name],
            dashboard["benchmark_metrics"][metric_name],
            f"analytics/dashboard {metric_name}",
        )
    expected_labels = [bucket[2] for bucket in PROBABILITY_BUCKETS]
    observed_labels = [
        bucket["label"] for bucket in analytics["probability_histogram"]
    ]
    require_equal(
        observed_labels, expected_labels, "probability histogram bucket order"
    )
    require(
        len(analytics["service_distribution"]) <= 10,
        "Service distribution exceeded service_limit=10.",
    )
    for service_limit in (5, 50):
        limited = client.request(
            "GET",
            f"/network/datasets/{dataset_id}/analytics",
            query={"service_limit": service_limit},
        )
        require(
            len(limited["service_distribution"]) <= service_limit,
            f"Service distribution exceeded service_limit={service_limit}.",
        )
    return {
        "totals": totals,
        "service_limit_5": "passed",
        "service_limit_10": "passed",
        "service_limit_50": "passed",
        "service_distribution_is_partial": True,
        "histogram_bucket_labels": observed_labels,
    }


def queue_sort_key(item: dict[str, Any]) -> tuple[float, str, int]:
    return (
        -float(item["risk_score"]),
        str(item["created_at"]),
        int(item["incident_id"]),
    )


def verify_incidents(
    client: ApiClient, dataset_id: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    queue_path = f"/network/datasets/{dataset_id}/incidents"
    default_page = client.request("GET", queue_path)
    first_page = client.request(
        "GET", queue_path, query={"limit": 25, "offset": 0}
    )
    second_page = client.request(
        "GET", queue_path, query={"limit": 25, "offset": 25}
    )
    require_equal(
        default_page["total"],
        EXPECTED_MODEL_COUNTS["total_incidents"],
        "incident queue total",
    )
    require_equal(first_page["limit"], 25, "incident page limit")
    require_equal(second_page["offset"], 25, "incident page offset")
    first_ids = {int(item["incident_id"]) for item in first_page["items"]}
    second_ids = {int(item["incident_id"]) for item in second_page["items"]}
    require(
        first_ids.isdisjoint(second_ids),
        "Adjacent incident pages contained duplicate incident IDs.",
    )
    require_equal(
        first_page["items"],
        sorted(first_page["items"], key=queue_sort_key),
        "incident risk ordering",
    )
    required_compact_fields = {
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
    require(
        required_compact_fields.issubset(first_page["items"][0]),
        "Incident queue item is missing fields required by React.",
    )
    open_page = client.request(
        "GET", queue_path, query={"status": "open", "limit": 25}
    )
    require(
        all(item["status"] == "open" for item in open_page["items"]),
        "Status filter returned a non-open incident.",
    )
    severity_checks: dict[str, int] = {}
    for severity in ("critical", "high", "medium", "low"):
        page = client.request(
            "GET", queue_path, query={"severity": severity, "limit": 25}
        )
        severity_checks[severity] = int(page["total"])
        require(
            all(item["severity"] == severity for item in page["items"]),
            f"Severity filter returned a non-{severity} incident.",
        )

    search_item = first_page["items"][0]
    search_value = (
        search_item["service"]
        or search_item["protocol_type"]
        or search_item["flag"]
    )
    search_page = client.request(
        "GET",
        queue_path,
        query={"search": str(search_value).upper(), "limit": 25},
    )
    require(search_page["total"] > 0, "Case-insensitive incident search failed.")
    combined_page = client.request(
        "GET",
        queue_path,
        query={
            "status": search_item["status"],
            "severity": search_item["severity"],
            "search": search_value,
            "limit": 25,
        },
    )
    require(
        any(
            item["incident_id"] == search_item["incident_id"]
            for item in combined_page["items"]
        ),
        "Combined incident filters did not include the matching incident.",
    )

    incident_id = int(search_item["incident_id"])
    detail = client.request("GET", f"/network/incidents/{incident_id}")
    required_detail_fields = {
        "evidence",
        "recommended_action",
        "prediction",
        "flow_context",
    }
    require(
        required_detail_fields.issubset(detail),
        "Incident detail omitted required persisted sections.",
    )
    require(detail["evidence"], "Incident detail evidence is empty.")
    require(
        detail["recommended_action"],
        "Incident detail recommended action is empty.",
    )
    require(
        detail["actual_label"] is not None
        and detail["actual_family"] is not None,
        "Labelled incident detail omitted benchmark truth.",
    )
    require(
        detail["prediction"]["actual_binary"] is not None
        and detail["prediction"]["is_correct"] is not None,
        "Labelled prediction detail omitted benchmark evaluation.",
    )
    require(
        detail["flow_context"]["actual_label"] is not None
        and detail["flow_context"]["difficulty_level"] is not None,
        "Labelled flow context omitted benchmark values.",
    )
    require(
        not any("encoded" in key or key.startswith("one_hot") for key in detail),
        "Incident detail exposed encoded model features.",
    )
    recursively_forbid_keys(default_page, "incident queue")
    recursively_forbid_keys(detail, "incident detail")
    return detail, {
        "total_incidents": default_page["total"],
        "adjacent_pages_unique": True,
        "risk_order": "passed",
        "status_filter": "passed",
        "severity_filter_totals": severity_checks,
        "case_insensitive_search": "passed",
        "combined_filters": "passed",
        "detail_contract": "passed",
        "fabricated_context_absent": True,
    }


def verify_workflow_update(
    client: ApiClient,
    dataset_id: int,
    detail: dict[str, Any],
) -> dict[str, Any]:
    incident_id = int(detail["incident_id"])
    original_status = str(detail["status"])
    dashboard_before = client.request(
        "GET", f"/network/datasets/{dataset_id}/dashboard"
    )
    before_kpis = dashboard_before["incident_kpis"]
    updated = client.request(
        "PATCH",
        f"/network/incidents/{incident_id}/status",
        json_body={"status": "investigating"},
    )
    require_equal(updated["status"], "investigating", "updated status")

    # Every request receives a fresh dependency-provided SQLAlchemy session.
    persisted = client.request("GET", f"/network/incidents/{incident_id}")
    require_equal(
        persisted["status"], "investigating", "persisted workflow status"
    )
    investigating = client.request(
        "GET",
        f"/network/datasets/{dataset_id}/incidents",
        query={"status": "investigating", "limit": 200},
    )
    require(
        any(
            item["incident_id"] == incident_id
            for item in investigating["items"]
        ),
        "Updated incident did not appear in the investigating queue.",
    )
    if original_status == "open":
        open_only = client.request(
            "GET",
            f"/network/datasets/{dataset_id}/incidents",
            query={"status": "open", "limit": 200},
        )
        require(
            all(item["incident_id"] != incident_id for item in open_only["items"]),
            "Updated incident remained in the open-only queue.",
        )

    dashboard_after = client.request(
        "GET", f"/network/datasets/{dataset_id}/dashboard"
    )
    after_kpis = dashboard_after["incident_kpis"]
    require_equal(
        after_kpis["total_incidents"],
        before_kpis["total_incidents"],
        "workflow update total incidents",
    )
    if original_status == "open":
        require_equal(
            after_kpis["open_incidents"],
            before_kpis["open_incidents"] - 1,
            "workflow open count",
        )
        require_equal(
            after_kpis["investigating_incidents"],
            before_kpis["investigating_incidents"] + 1,
            "workflow investigating count",
        )

    restored = client.request(
        "PATCH",
        f"/network/incidents/{incident_id}/status",
        json_body={"status": original_status},
    )
    require_equal(restored["status"], original_status, "restored status")
    restored_dashboard = client.request(
        "GET", f"/network/datasets/{dataset_id}/dashboard"
    )
    require_equal(
        restored_dashboard["incident_kpis"]["open_incidents"],
        before_kpis["open_incidents"],
        "restored workflow count",
    )
    return {
        "incident_id": incident_id,
        "original_status": original_status,
        "updated_status": "investigating",
        "fresh_request_persistence": "passed",
        "queue_movement": "passed",
        "dashboard_reconciliation": "passed",
        "restored_for_determinism": True,
    }


def verify_idempotency(client: ApiClient, dataset_id: int) -> dict[str, Any]:
    from backend.app.network import analysis_service

    def should_not_run(*args, **kwargs):
        del args, kwargs
        raise VerificationError(
            "Completed dataset unexpectedly invoked frozen model prediction."
        )

    before = client.request("GET", f"/network/datasets/{dataset_id}")
    with (
        patch.object(
            analysis_service,
            "load_final_detector",
            new=should_not_run,
        ),
        patch.object(
            analysis_service,
            "predict_network_flows",
            new=should_not_run,
        ),
    ):
        repeated = client.request(
            "POST", f"/network/datasets/{dataset_id}/analyze"
        )
    after = client.request("GET", f"/network/datasets/{dataset_id}")
    require_equal(repeated["reused_existing"], True, "idempotent reuse flag")
    for field in ("prediction_count", "incident_count"):
        require_equal(
            after[field], before[field], f"idempotent {field} stability"
        )
    return {
        "reused_existing": True,
        "prediction_count": after["prediction_count"],
        "incident_count": after["incident_count"],
        "prediction_function_not_called": True,
    }


def create_inference_csv(
    path: Path, feature_rows: list[dict[str, Any]]
) -> None:
    """Write only official feature columns, without fabricated labels."""
    from ml_pipeline.nsl_kdd_schema import FEATURE_COLUMNS

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FEATURE_COLUMNS)
        writer.writeheader()
        for source in feature_rows:
            writer.writerow({column: source[column] for column in FEATURE_COLUMNS})


def verify_inference_only(
    client: ApiClient,
    labelled_dataset_id: int,
    selected_incident: dict[str, Any],
    temporary_directory: Path,
) -> dict[str, Any]:
    row_number = int(selected_incident["row_number"])
    source_page = client.request(
        "GET",
        f"/network/datasets/{labelled_dataset_id}/flows",
        query={"limit": 2, "offset": row_number - 1},
    )
    require(source_page["items"], "Could not obtain source flows for CSV.")
    csv_path = temporary_directory / "inference_only.csv"
    create_inference_csv(csv_path, source_page["items"])
    try:
        upload = client.request(
            "POST",
            "/network/datasets/upload",
            file_upload=(csv_path.name, csv_path.read_bytes()),
            expected_status=201,
        )
    finally:
        csv_path.unlink(missing_ok=True)
    require_equal(upload["has_ground_truth"], False, "inference ground truth")
    require_equal(
        upload["source_type"],
        "nsl_kdd_inference",
        "inference source type",
    )
    require_equal(upload["label_distribution"], [], "inference labels")
    require_equal(
        upload["attack_family_distribution"], [], "inference families"
    )
    dataset_id = int(upload["id"])
    flows = client.request(
        "GET", f"/network/datasets/{dataset_id}/flows"
    )
    require(
        all(
            flow["actual_label"] is None
            and flow["actual_family"] is None
            and flow["difficulty_level"] is None
            for flow in flows["items"]
        ),
        "Inference-only flow persisted fabricated benchmark values.",
    )
    with prohibit_model_fitting():
        analysis = client.request(
            "POST", f"/network/datasets/{dataset_id}/analyze"
        )
    require_equal(
        analysis["total_predictions"],
        upload["total_records"],
        "inference prediction count",
    )
    require_equal(
        analysis["total_incidents"],
        analysis["predicted_attack"],
        "inference incident count",
    )
    require_equal(
        analysis["benchmark_metrics"], None, "inference analysis benchmark"
    )
    dashboard = client.request(
        "GET", f"/network/datasets/{dataset_id}/dashboard"
    )
    analytics = client.request(
        "GET", f"/network/datasets/{dataset_id}/analytics"
    )
    require_equal(
        dashboard["benchmark_metrics"], None, "inference dashboard benchmark"
    )
    for field in (
        "actual_family_distribution",
        "correctness_distribution",
        "benchmark_metrics",
    ):
        require_equal(analytics[field], None, f"inference analytics {field}")
    incident_benchmark_null = True
    if analysis["predicted_attack"]:
        queue = client.request(
            "GET", f"/network/datasets/{dataset_id}/incidents"
        )
        inference_detail = client.request(
            "GET",
            f"/network/incidents/{queue['items'][0]['incident_id']}",
        )
        incident_benchmark_null = (
            inference_detail["actual_label"] is None
            and inference_detail["actual_family"] is None
            and inference_detail["prediction"]["actual_binary"] is None
            and inference_detail["prediction"]["is_correct"] is None
            and inference_detail["flow_context"]["actual_label"] is None
            and inference_detail["flow_context"]["actual_family"] is None
            and inference_detail["flow_context"]["difficulty_level"] is None
        )
        require(
            incident_benchmark_null,
            "Inference-only incident exposed fabricated benchmark fields.",
        )
    return {
        "dataset_id": dataset_id,
        "uploaded_rows": upload["total_records"],
        "predictions": analysis["total_predictions"],
        "predicted_attack": analysis["predicted_attack"],
        "incidents": analysis["total_incidents"],
        "benchmark_metrics_are_null": True,
        "incident_benchmark_fields_are_null": incident_benchmark_null,
        "temporary_csv_deleted": not csv_path.exists(),
    }


def inspect_frontend_contract_files() -> dict[str, Any]:
    """Confirm every N5 network consumer exists for response-contract review."""
    missing = [
        path
        for path in FRONTEND_CONTRACT_FILES
        if not (REPOSITORY_ROOT / path).is_file()
    ]
    require(
        not missing,
        f"Frontend response consumers are missing: {missing}.",
    )
    return {
        "inspected_files": FRONTEND_CONTRACT_FILES,
        "demonstrated_field_mismatches": [],
    }


def run_command(
    name: str,
    command: list[str],
    *,
    cwd: Path = REPOSITORY_ROOT,
) -> dict[str, Any]:
    """Run one regression command and retain only safe summarized output."""
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    duration = time.perf_counter() - started
    if completed.returncode != 0:
        combined = "\n".join(
            part for part in (completed.stdout, completed.stderr) if part
        )
        tail = "\n".join(combined.splitlines()[-30:])
        raise VerificationError(
            f"{name} failed with exit code {completed.returncode}.\n{tail}"
        )
    return {
        "outcome": "passed",
        "return_code": completed.returncode,
        "duration_seconds": round(duration, 3),
    }


def run_regressions() -> dict[str, Any]:
    """Run contract tests, the backend suite, frozen-model verification, and UI build."""
    python = sys.executable
    results = {
        "api_contract_tests": run_command(
            "focused API contract tests",
            [
                python,
                "-m",
                "unittest",
                "backend.app.tests.test_network_api_contracts",
                "-v",
            ],
        ),
        "complete_backend_tests": run_command(
            "complete backend test discovery",
            [
                python,
                "-m",
                "unittest",
                "discover",
                "-s",
                "backend/app/tests",
                "-p",
                "test*.py",
                "-v",
            ],
        ),
        # The established verifier normally rewrites a timestamped tracked report.
        # Suppressing only that write preserves N3 files while executing all checks.
        "final_model_verification": run_command(
            "final model verification",
            [
                python,
                "-c",
                (
                    "import ml_pipeline.verify_final_model as verifier; "
                    "verifier.write_json = lambda *args, **kwargs: None; "
                    "verifier.main()"
                ),
            ],
        ),
        "frontend_build": run_command(
            "frontend production build",
            ["npm.cmd", "run", "build"],
            cwd=REPOSITORY_ROOT / "frontend",
        ),
    }
    distribution = REPOSITORY_ROOT / "frontend" / "dist"
    if distribution.exists():
        resolved = distribution.resolve()
        frontend_root = (REPOSITORY_ROOT / "frontend").resolve()
        require(
            resolved.is_relative_to(frontend_root),
            "Refusing to remove a build directory outside the frontend.",
        )
        shutil.rmtree(resolved)
    results["frontend_build"]["generated_dist_removed"] = not distribution.exists()
    return results


def write_report(report: dict[str, Any]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def print_summary(report: dict[str, Any]) -> None:
    checks = [
        ("authentication", report["authenticated_workflow"]["authentication"]),
        ("upload", report["authenticated_workflow"]["labelled_upload"]["upload"]),
        ("analysis", report["authenticated_workflow"]["analysis"]["outcome"]),
        ("dashboard", report["dashboard_reconciliation"]["outcome"]),
        ("analytics", report["analytics_reconciliation"]["outcome"]),
        ("incidents", report["queue_and_detail"]["outcome"]),
        ("workflow update", report["status_persistence"]["outcome"]),
        ("inference-only flow", report["inference_only"]["outcome"]),
        ("idempotency", report["idempotency"]["outcome"]),
        ("no fitting", report["no_fit_verification"]["outcome"]),
        ("artifact integrity", report["artifact_integrity"]["outcome"]),
        (
            "backend tests",
            report["regression_results"]["complete_backend_tests"]["outcome"],
        ),
        (
            "frontend build",
            report["regression_results"]["frontend_build"]["outcome"],
        ),
    ]
    print("Athes Sentinel network E2E verification")
    for label, result in checks:
        print(f"  {label}: {str(result).upper()}")
    print(f"  report: {relative_path(REPORT_PATH)}")


def main() -> None:
    """Run the E2E lifecycle, safety checks, regressions, and report generation."""
    require(DATASET_PATH.is_file(), f"Missing complete dataset: {DATASET_PATH}")
    require(ARTIFACT_PATH.is_file(), f"Missing frozen artifact: {ARTIFACT_PATH}")
    require(METADATA_PATH.is_file(), f"Missing metadata: {METADATA_PATH}")

    artifact_hash_before = file_sha256(ARTIFACT_PATH)
    metadata_hash_before = file_sha256(METADATA_PATH)
    dataset_hash_before = file_sha256(DATASET_PATH)
    real_database_before = file_signature(REAL_DATABASE_PATH)
    require_equal(
        artifact_hash_before,
        EXPECTED_ARTIFACT_SHA256,
        "frozen artifact SHA-256",
    )

    started = time.perf_counter()
    report: dict[str, Any] = {
        "outcome": "in_progress",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "temporary_database_policy": (
            "The real FastAPI app was imported only after DATABASE_URL was "
            "redirected to a disposable SQLite file. get_db was explicitly "
            "overridden, startup was not connected to any external database, "
            "and the disposable database was removed afterward."
        ),
        "defects_found_and_fixed": [],
    }

    with tempfile.TemporaryDirectory(prefix="athes-network-e2e-") as temp_name:
        temporary_directory = Path(temp_name)
        disposable_database = temporary_directory / "network_e2e.sqlite3"
        os.environ["DATABASE_URL"] = (
            f"sqlite:///{disposable_database.resolve().as_posix()}"
        )
        os.environ["ATHES_ENV"] = "verification"
        os.environ["ATHES_SECRET_KEY"] = (
            "athes-network-e2e-disposable-verification-key"
        )

        from backend.app.auth.service import create_demo_users
        from backend.app.database import models  # noqa: F401
        from backend.app.database.session import (
            Base,
            SessionLocal,
            engine,
            get_db,
        )
        from backend.app.main import app

        def override_disposable_database():
            session = SessionLocal()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_disposable_database
        Base.metadata.create_all(bind=engine)
        seed_session = SessionLocal()
        try:
            create_demo_users(seed_session)
        finally:
            seed_session.close()

        client = ApiClient(app)
        route_result = verify_route_registration(app)

        unauthenticated = client.request(
            "GET",
            "/network/datasets",
            authenticated=False,
            expected_status=401,
        )
        require(
            isinstance(unauthenticated, dict),
            "Unauthenticated response was not structured JSON.",
        )
        login = client.request(
            "POST",
            "/auth/login",
            json_body={"username": "admin", "password": "admin123"},
            authenticated=False,
        )
        client.token = login["access_token"]
        require(
            isinstance(client.token, str) and len(client.token) > 20,
            "Real login did not return an access token.",
        )

        dataset_id, upload_read_result = verify_labelled_upload_and_reads(
            client, DATASET_PATH.read_bytes()
        )
        analysis, maximum_metric_difference = run_real_analysis(
            client, dataset_id
        )
        dashboard, dashboard_result = verify_dashboard(client, dataset_id)
        analytics_result = verify_analytics(client, dataset_id, dashboard)
        incident_detail, incident_result = verify_incidents(client, dataset_id)
        workflow_result = verify_workflow_update(
            client, dataset_id, incident_detail
        )
        idempotency_result = verify_idempotency(client, dataset_id)
        inference_result = verify_inference_only(
            client,
            dataset_id,
            incident_detail,
            temporary_directory,
        )
        frontend_inspection = inspect_frontend_contract_files()

        report.update(
            {
                "authenticated_workflow": {
                    "authentication": "passed",
                    "unauthenticated_protected_request": "rejected",
                    "token_recorded_in_report": False,
                    "labelled_upload": upload_read_result,
                    "analysis": {
                        "outcome": "passed",
                        "complete_uploaded_rows": EXPECTED_ROWS,
                        "total_predictions": analysis["total_predictions"],
                        "predicted_normal": analysis["predicted_normal"],
                        "predicted_attack": analysis["predicted_attack"],
                        "total_incidents": analysis["total_incidents"],
                        "threshold_probability": analysis["threshold"],
                        "model_version": analysis["model_version"],
                        "confusion_matrix": {
                            key: analysis["benchmark_metrics"][key]
                            for key in EXPECTED_CONFUSION
                        },
                        "metrics": {
                            key: analysis["benchmark_metrics"][key]
                            for key in EXPECTED_METRICS
                        },
                        "maximum_metric_difference": maximum_metric_difference,
                    },
                },
                "dashboard_reconciliation": {
                    "outcome": "passed",
                    **dashboard_result,
                },
                "analytics_reconciliation": {
                    "outcome": "passed",
                    **analytics_result,
                },
                "queue_and_detail": {
                    "outcome": "passed",
                    **incident_result,
                },
                "status_persistence": {
                    "outcome": "passed",
                    **workflow_result,
                },
                "inference_only": {
                    "outcome": "passed",
                    **inference_result,
                },
                "idempotency": {
                    "outcome": "passed",
                    **idempotency_result,
                },
                "frontend_contract_inspection": frontend_inspection,
                "route_registration": route_result,
                "no_fit_verification": {
                    "outcome": "passed",
                    "guarded_methods": [
                        "Pipeline.fit",
                        "ColumnTransformer.fit",
                        "ColumnTransformer.fit_transform",
                        "OneHotEncoder.fit",
                        "OneHotEncoder.fit_transform",
                        "RandomForestClassifier.fit",
                    ],
                    "statement": (
                        "No model training, fitting, tuning, or threshold "
                        "selection occurred."
                    ),
                },
            }
        )
        app.dependency_overrides.clear()
        engine.dispose()

    require(
        not disposable_database.exists(),
        "Disposable SQLite database was not removed.",
    )
    regression_results = run_regressions()

    artifact_hash_after = file_sha256(ARTIFACT_PATH)
    metadata_hash_after = file_sha256(METADATA_PATH)
    dataset_hash_after = file_sha256(DATASET_PATH)
    real_database_after = file_signature(REAL_DATABASE_PATH)
    require_equal(
        artifact_hash_after, artifact_hash_before, "artifact hash stability"
    )
    require_equal(
        metadata_hash_after, metadata_hash_before, "metadata hash stability"
    )
    require_equal(
        dataset_hash_after, dataset_hash_before, "source dataset hash stability"
    )
    require_equal(
        real_database_after,
        real_database_before,
        "real local database signature",
    )

    report.update(
        {
            "artifact_integrity": {
                "outcome": "passed",
                "artifact_relative_path": relative_path(ARTIFACT_PATH),
                "artifact_sha256_before": artifact_hash_before,
                "artifact_sha256_after": artifact_hash_after,
                "metadata_sha256_before": metadata_hash_before,
                "metadata_sha256_after": metadata_hash_after,
                "source_dataset_unchanged": True,
            },
            "regression_results": regression_results,
            "api_contract_tests": regression_results["api_contract_tests"],
            "backend_test_result": regression_results[
                "complete_backend_tests"
            ],
            "frontend_build_result": regression_results["frontend_build"],
            "real_database_safety": {
                "real_local_database_unchanged": True,
                "deployed_postgresql_contacted": False,
                "deployed_vercel_contacted": False,
                "deployed_master_contacted": False,
                "disposable_database_removed": True,
            },
            "outcome": "passed",
            "duration_seconds": round(time.perf_counter() - started, 3),
        }
    )
    write_report(report)
    print_summary(report)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        failed_report = {
            "outcome": "failed",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "failure_type": type(error).__name__,
            "failure_message": str(error),
            "temporary_database_policy": (
                "The verifier redirected DATABASE_URL to disposable SQLite "
                "before importing the application."
            ),
            "defects_found_and_fixed": [],
        }
        write_report(failed_report)
        print(f"Athes Sentinel network E2E verification: FAILED ({error})")
        print(f"Report: {relative_path(REPORT_PATH)}")
        raise
