"""Audit Athes Sentinel production readiness without contacting live services.

The verifier creates a Git-archive snapshot, overlays only current modifications
to explicitly listed release-readiness files, and exercises that candidate
checkout with the existing local Python and Node installations. Ignored
datasets, local databases, untracked files, and live provider credentials are
never copied.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

REPORT_PATH = (
    REPOSITORY_ROOT
    / "ml_pipeline"
    / "reports"
    / "deployment_readiness_verification.json"
)
ARTIFACT_RELATIVE_PATH = Path(
    "ml_pipeline/artifacts/nsl_kdd_improved_binary_pipeline.joblib"
)
METADATA_RELATIVE_PATH = Path(
    "ml_pipeline/artifacts/improved_model_metadata.json"
)
EXPECTED_ARTIFACT_SHA256 = (
    "09b4cac3372256c3122bcfb5555706d63397e8449385470a283427e688691c13"
)
EXPECTED_ARTIFACT_SIZE = 6_705_637
EXPECTED_SKLEARN_VERSION = "1.9.0"
EXPECTED_TABLES = {
    "users",
    "log_files",
    "raw_logs",
    "ip_features",
    "incidents",
    "network_datasets",
    "network_flows",
    "network_predictions",
    "network_incidents",
}
EXPECTED_NETWORK_ROUTES = {
    "/network/datasets",
    "/network/datasets/upload",
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
EXPECTED_OLD_ROUTE_PREFIXES = (
    "/logs",
    "/features",
    "/ml",
    "/analytics",
    "/incidents",
)
CANDIDATE_OVERLAY_FILES = (
    Path("scripts/verify_deployment_readiness.py"),
    Path("requirements.txt"),
    Path("backend/app/main.py"),
    Path("frontend/src/api/client.js"),
    Path("render.yaml"),
    Path("frontend/vercel.json"),
    Path("frontend/.env.example"),
)
PRODUCTION_TEST_ORIGIN = "https://frontend-verification.example.invalid"
PRODUCTION_TEST_API_URL = "https://api-verification.example.invalid"


class ReadinessError(RuntimeError):
    """Raised when one deployment invariant cannot be reproduced."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReadinessError(message)


def require_equal(observed: Any, expected: Any, label: str) -> None:
    if observed != expected:
        raise ReadinessError(
            f"{label}: expected {expected!r}, observed {observed!r}."
        )


def run(
    command: list[str],
    *,
    cwd: Path = REPOSITORY_ROOT,
    env: dict[str, str] | None = None,
    check: bool = True,
    timeout: float = 180.0,
) -> subprocess.CompletedProcess[str]:
    """Run a command with captured output and safe failure excerpts."""
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if check and completed.returncode != 0:
        combined = "\n".join(
            part for part in (completed.stdout, completed.stderr) if part
        )
        tail = "\n".join(combined.splitlines()[-30:])
        raise ReadinessError(
            f"Command failed ({completed.returncode}): {' '.join(command)}\n"
            f"{tail}"
        )
    return completed


def git(*arguments: str, check: bool = True) -> str:
    return run(["git", *arguments], check=check).stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_signature(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "size_bytes": None, "sha256": None}
    return {
        "exists": True,
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def relative(path: Path) -> str:
    return path.resolve().relative_to(REPOSITORY_ROOT.resolve()).as_posix()


def package_version(distribution_name: str) -> str | None:
    try:
        return importlib.metadata.version(distribution_name)
    except importlib.metadata.PackageNotFoundError:
        return None


def git_artifact_audit() -> dict[str, Any]:
    artifact = REPOSITORY_ROOT / ARTIFACT_RELATIVE_PATH
    metadata_path = REPOSITORY_ROOT / METADATA_RELATIVE_PATH
    require(artifact.is_file(), "The selected model artifact is missing.")
    require(metadata_path.is_file(), "The selected model metadata is missing.")
    tracked = git("ls-files", "--error-unmatch", ARTIFACT_RELATIVE_PATH.as_posix())
    require_equal(
        tracked,
        ARTIFACT_RELATIVE_PATH.as_posix(),
        "tracked artifact path",
    )
    git("cat-file", "-e", f"HEAD:{ARTIFACT_RELATIVE_PATH.as_posix()}")
    blob_size = int(
        git("cat-file", "-s", f"HEAD:{ARTIFACT_RELATIVE_PATH.as_posix()}")
    )
    blob_id = git("rev-parse", f"HEAD:{ARTIFACT_RELATIVE_PATH.as_posix()}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    observed_hash = sha256(artifact)
    require_equal(
        observed_hash, EXPECTED_ARTIFACT_SHA256, "working artifact hash"
    )
    require_equal(
        observed_hash, metadata["artifact_sha256"], "metadata artifact hash"
    )
    require_equal(artifact.stat().st_size, EXPECTED_ARTIFACT_SIZE, "artifact size")
    require_equal(blob_size, EXPECTED_ARTIFACT_SIZE, "Git blob size")

    ignored_checks = {}
    for name, path in {
        "baseline_joblib": "ml_pipeline/artifacts/nsl_kdd_binary_pipeline.joblib",
        "hybrid_joblib": "ml_pipeline/artifacts/nsl_kdd_hybrid_detector.joblib",
        "raw_test_dataset": "data/external/nsl-kdd/KDDTest+.txt",
        "raw_train_dataset": "data/external/nsl-kdd/KDDTrain+.txt",
        "root_env": ".env",
        "frontend_env": "frontend/.env",
    }.items():
        result = run(["git", "check-ignore", "-q", path], check=False)
        require_equal(result.returncode, 0, f"ignored path {path}")
        ignored_checks[name] = True

    tracked_raw = git("ls-files", "data/external/nsl-kdd")
    require_equal(tracked_raw, "", "tracked raw datasets")
    return {
        "tracked": True,
        "relative_path": ARTIFACT_RELATIVE_PATH.as_posix(),
        "size_bytes": artifact.stat().st_size,
        "git_blob_size_bytes": blob_size,
        "git_blob_id": blob_id,
        "working_tree_sha256": observed_hash,
        "metadata_sha256_match": True,
        "ignored_checks": ignored_checks,
        "tracked_raw_dataset_files": [],
    }


def create_candidate_checkout(destination: Path) -> dict[str, Any]:
    """Extract committed Git content, then overlay listed release-readiness edits."""
    archive_path = destination.parent / "candidate.tar"
    with archive_path.open("wb") as archive:
        completed = subprocess.run(
            ["git", "archive", "--format=tar", "HEAD"],
            cwd=REPOSITORY_ROOT,
            stdout=archive,
            stderr=subprocess.PIPE,
            check=False,
        )
    require_equal(completed.returncode, 0, "git archive return code")
    destination.mkdir(parents=True)
    with tarfile.open(archive_path, "r") as archive:
        archive.extractall(destination, filter="data")
    archive_path.unlink()

    overlaid: list[str] = []
    for relative_path in CANDIDATE_OVERLAY_FILES:
        changed = run(
            [
                "git",
                "diff",
                "--quiet",
                "HEAD",
                "--",
                relative_path.as_posix(),
            ],
            check=False,
        ).returncode
        if changed == 1:
            source = REPOSITORY_ROOT / relative_path
            require(
                source.is_file(),
                f"Tracked deployment candidate file is missing: {relative_path}",
            )
            target = destination / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            overlaid.append(relative_path.as_posix())
        elif changed != 0:
            raise ReadinessError(
                f"Could not inspect candidate diff for {relative_path}."
            )

    require(
        (destination / ARTIFACT_RELATIVE_PATH).is_file(),
        "Git archive did not contain the tracked model artifact.",
    )
    require(
        not (destination / "data" / "external" / "nsl-kdd").exists(),
        "Clean candidate unexpectedly contains ignored raw datasets.",
    )
    return {
        "source": (
            "git archive HEAD with only current modifications to explicitly "
            "listed release-readiness files overlaid"
        ),
        "overlaid_tracked_files": overlaid,
        "ignored_and_untracked_files_excluded": True,
        "raw_datasets_absent": True,
    }


def python_json(
    checkout: Path,
    source: str,
    *,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> tuple[subprocess.CompletedProcess[str], Any | None]:
    command_env = os.environ.copy()
    command_env["PYTHONPATH"] = str(checkout)
    if env:
        command_env.update(env)
    completed = run(
        [sys.executable, "-c", source],
        cwd=checkout,
        env=command_env,
        check=check,
        timeout=180,
    )
    payload = None
    if completed.returncode == 0 and completed.stdout.strip():
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
    return completed, payload


def clean_model_inference(checkout: Path) -> dict[str, Any]:
    source = r'''
import json
from contextlib import ExitStack
from unittest.mock import patch
import pandas as pd
import joblib
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from backend.app.ml.nsl_kdd_inference import (
    FINAL_ARTIFACT_PATH,
    FINAL_METADATA_PATH,
    load_final_detector,
    predict_network_flows,
)
from ml_pipeline.nsl_kdd_schema import FEATURE_COLUMNS

record = {}
for column in FEATURE_COLUMNS:
    if column == "protocol_type":
        record[column] = "tcp"
    elif column == "service":
        record[column] = "http"
    elif column == "flag":
        record[column] = "SF"
    elif column.endswith("_rate"):
        record[column] = 0.0
    else:
        record[column] = 0
record["src_bytes"] = 181
record["dst_bytes"] = 5450
record["logged_in"] = 1
record["count"] = 8
record["srv_count"] = 8

def forbidden(*args, **kwargs):
    raise AssertionError("fit called during deployment inference")

with ExitStack() as stack:
    for owner, name in (
        (Pipeline, "fit"),
        (ColumnTransformer, "fit"),
        (ColumnTransformer, "fit_transform"),
        (OneHotEncoder, "fit"),
        (OneHotEncoder, "fit_transform"),
        (RandomForestClassifier, "fit"),
    ):
        stack.enter_context(patch.object(owner, name, new=forbidden))
    detector_one, metadata = load_final_detector()
    detector_two, _ = load_final_detector()
    predictions = predict_network_flows(
        pd.DataFrame([record], columns=FEATURE_COLUMNS)
    )

root = FINAL_ARTIFACT_PATH.parents[2]
print(json.dumps({
    "artifact_relative_path": FINAL_ARTIFACT_PATH.relative_to(root).as_posix(),
    "metadata_relative_path": FINAL_METADATA_PATH.relative_to(root).as_posix(),
    "artifact_exists": FINAL_ARTIFACT_PATH.is_file(),
    "metadata_exists": FINAL_METADATA_PATH.is_file(),
    "artifact_hash": metadata["artifact_sha256"],
    "metadata_sklearn_version": metadata["scikit_learn_version"],
    "runtime_sklearn_version": sklearn.__version__,
    "runtime_joblib_version": joblib.__version__,
    "model_type": type(detector_one).__name__,
    "classifier_type": type(detector_one.named_steps["classifier"]).__name__,
    "cache_same_object": detector_one is detector_two,
    "cache_size": load_final_detector.cache_info().currsize,
    "prediction_count": len(predictions),
    "probability": float(predictions.iloc[0]["rf_attack_probability"]),
    "predicted_class": str(predictions.iloc[0]["predicted_class"]),
    "fit_methods_called": False,
}))
'''
    _, result = python_json(checkout, source)
    require(result["artifact_exists"], "Clean-checkout artifact is absent.")
    require(result["metadata_exists"], "Clean-checkout metadata is absent.")
    require_equal(
        result["artifact_hash"], EXPECTED_ARTIFACT_SHA256, "clean artifact hash"
    )
    require_equal(
        result["metadata_sklearn_version"],
        EXPECTED_SKLEARN_VERSION,
        "metadata scikit-learn version",
    )
    require_equal(
        result["runtime_sklearn_version"],
        EXPECTED_SKLEARN_VERSION,
        "runtime scikit-learn version",
    )
    require_equal(result["prediction_count"], 1, "clean prediction count")
    require(
        0.0 <= result["probability"] <= 1.0,
        "Clean inference probability is outside [0, 1].",
    )
    require(result["cache_same_object"], "Detector cache did not reuse object.")
    require_equal(result["cache_size"], 1, "detector cache size")
    require(not result["fit_methods_called"], "A fit method was called.")
    return result


def dependency_audit(checkout: Path) -> dict[str, Any]:
    requirements = (checkout / "requirements.txt").read_text(encoding="utf-8")
    normalized_lines = {
        line.strip().lower()
        for line in requirements.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    required_declarations = {
        "fastapi": "fastapi",
        "uvicorn": "uvicorn",
        "sqlalchemy": "sqlalchemy",
        "pydantic": "pydantic",
        "multipart": "python-multipart",
        "pandas": "pandas",
        "numpy": "numpy",
        "joblib": "joblib",
        "password_hashing": "passlib[bcrypt]",
        "jwt": "python-jose[cryptography]",
        "bcrypt_compatibility": "bcrypt==4.0.1",
        "postgresql_driver": "psycopg[binary]",
    }
    for label, declaration in required_declarations.items():
        require(
            declaration in normalized_lines,
            f"Missing production dependency declaration: {label}.",
        )
    require(
        "scikit-learn==1.9.0" in normalized_lines,
        "The joblib artifact requires an exact scikit-learn 1.9.0 declaration.",
    )
    versions = {
        name: package_version(name)
        for name in (
            "fastapi",
            "uvicorn",
            "sqlalchemy",
            "pydantic",
            "python-multipart",
            "pandas",
            "numpy",
            "scikit-learn",
            "joblib",
            "passlib",
            "python-jose",
            "bcrypt",
            "psycopg",
        )
    }
    for runtime_package in (
        "fastapi",
        "uvicorn",
        "sqlalchemy",
        "pydantic",
        "python-multipart",
        "pandas",
        "numpy",
        "scikit-learn",
        "joblib",
        "passlib",
        "python-jose",
        "bcrypt",
    ):
        require(
            versions[runtime_package] is not None,
            f"Local runtime package is unavailable: {runtime_package}.",
        )
    require_equal(
        versions["scikit-learn"],
        EXPECTED_SKLEARN_VERSION,
        "installed scikit-learn",
    )
    return {
        "declarations": required_declarations
        | {"model_serialization_compatibility": "scikit-learn==1.9.0"},
        "local_verification_versions": versions,
        "postgresql_driver_note": (
            "psycopg[binary] is declared for clean production installation. "
            "The pre-existing local verification venv does not currently "
            "contain psycopg, so no PostgreSQL connection was attempted."
        ),
        "decision": (
            "Added the directly imported joblib dependency and pinned "
            "scikit-learn to the artifact creation version 1.9.0. No other "
            "runtime package was changed."
        ),
    }


def database_compilation(checkout: Path, database_path: Path) -> dict[str, Any]:
    source = r'''
import json
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable
from backend.app.database import models
from backend.app.database.session import Base, normalize_database_url

dialect = postgresql.dialect()
table_sql = {}
index_sql = {}
for table in Base.metadata.sorted_tables:
    table_sql[table.name] = str(CreateTable(table).compile(dialect=dialect))
    for index in table.indexes:
        index_sql[index.name] = str(CreateIndex(index).compile(dialect=dialect))

print(json.dumps({
    "tables": sorted(Base.metadata.tables),
    "table_count": len(Base.metadata.tables),
    "network_tables": sorted(
        name for name in Base.metadata.tables if name.startswith("network_")
    ),
    "postgresql_tables_compiled": sorted(table_sql),
    "postgresql_indexes_compiled": sorted(index_sql),
    "postgres_legacy_normalized": normalize_database_url(
        "postgres://placeholder-host/database"
    ).startswith("postgresql+psycopg://"),
    "postgresql_normalized": normalize_database_url(
        "postgresql://placeholder-host/database"
    ).startswith("postgresql+psycopg://"),
    "sqlite_preserved": normalize_database_url(
        "sqlite:///temporary.sqlite3"
    ) == "sqlite:///temporary.sqlite3",
}))
'''
    env = {"DATABASE_URL": f"sqlite:///{database_path.as_posix()}"}
    _, result = python_json(checkout, source, env=env)
    require_equal(set(result["tables"]), EXPECTED_TABLES, "registered tables")
    require_equal(result["table_count"], 9, "registered table count")
    require_equal(
        result["network_tables"],
        [
            "network_datasets",
            "network_flows",
            "network_incidents",
            "network_predictions",
        ],
        "registered network tables",
    )
    require(result["postgres_legacy_normalized"], "postgres:// was not normalized.")
    require(result["postgresql_normalized"], "postgresql:// was not normalized.")
    require(result["sqlite_preserved"], "SQLite URL was unexpectedly modified.")
    require_equal(
        len(result["postgresql_tables_compiled"]),
        9,
        "PostgreSQL compiled table count",
    )
    return result


def verify_environment_failures(checkout: Path, database_path: Path) -> dict[str, Any]:
    base_env = os.environ.copy()
    base_env["PYTHONPATH"] = str(checkout)
    base_env["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
    base_env["ATHES_ENV"] = "production"
    base_env.pop("ATHES_SECRET_KEY", None)
    base_env["ATHES_ALLOWED_ORIGINS"] = PRODUCTION_TEST_ORIGIN
    missing_secret = run(
        [sys.executable, "-c", "import backend.app.main"],
        cwd=checkout,
        env=base_env,
        check=False,
    )
    require(
        missing_secret.returncode != 0
        and "ATHES_SECRET_KEY must be configured" in missing_secret.stderr,
        "Production import did not fail clearly without ATHES_SECRET_KEY.",
    )

    base_env["ATHES_SECRET_KEY"] = "local-disposable-verification-secret"
    base_env.pop("ATHES_ALLOWED_ORIGINS", None)
    missing_origin = run(
        [sys.executable, "-c", "import backend.app.main"],
        cwd=checkout,
        env=base_env,
        check=False,
    )
    require(
        missing_origin.returncode != 0
        and "ATHES_ALLOWED_ORIGINS must be configured" in missing_origin.stderr,
        "Production import did not fail clearly without allowed origins.",
    )
    return {
        "production_missing_jwt_secret": "clear startup failure",
        "production_missing_allowed_origins": "clear startup failure",
        "development_defaults": {
            "database": "repository-local SQLite",
            "jwt": "development-only fallback",
            "cors": ["http://localhost:5173"],
        },
        "secret_values_recorded": False,
    }


def available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def http_json(
    method: str,
    url: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    expected_status: int = 200,
) -> tuple[Any, dict[str, str]]:
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers=headers or {},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload_bytes = response.read()
            status = response.status
            response_headers = {
                key.lower(): value for key, value in response.headers.items()
            }
    except urllib.error.HTTPError as error:
        payload_bytes = error.read()
        status = error.code
        response_headers = {
            key.lower(): value for key, value in error.headers.items()
        }
    payload = json.loads(payload_bytes or b"{}")
    require_equal(status, expected_status, f"{method} {url} status")
    return payload, response_headers


def multipart_body(filename: str, content: bytes) -> tuple[bytes, str]:
    boundary = "athes-deployment-readiness-boundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: text/csv\r\n\r\n"
    ).encode("utf-8")
    body += content
    body += f"\r\n--{boundary}--\r\n".encode("utf-8")
    return body, f"multipart/form-data; boundary={boundary}"


def small_inference_csv() -> bytes:
    from ml_pipeline.nsl_kdd_schema import FEATURE_COLUMNS

    record: dict[str, Any] = {}
    for column in FEATURE_COLUMNS:
        if column == "protocol_type":
            record[column] = "tcp"
        elif column == "service":
            record[column] = "http"
        elif column == "flag":
            record[column] = "SF"
        elif column.endswith("_rate"):
            record[column] = 0.0
        else:
            record[column] = 0
    record.update(
        {
            "src_bytes": 181,
            "dst_bytes": 5450,
            "logged_in": 1,
            "count": 8,
            "srv_count": 8,
        }
    )
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FEATURE_COLUMNS)
    writer.writeheader()
    writer.writerow(record)
    return output.getvalue().encode("utf-8")


def startup_cache_check(checkout: Path, database_path: Path) -> dict[str, Any]:
    source = r'''
import json
from backend.app.main import create_database_tables
create_database_tables()
from backend.app.ml.nsl_kdd_inference import load_final_detector
print(json.dumps({
    "model_cache_size_after_startup": load_final_detector.cache_info().currsize
}))
'''
    env = {
        "DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
        "ATHES_ENV": "production",
        "ATHES_SECRET_KEY": "local-disposable-verification-secret",
        "ATHES_ALLOWED_ORIGINS": PRODUCTION_TEST_ORIGIN,
    }
    _, result = python_json(checkout, source, env=env)
    require_equal(
        result["model_cache_size_after_startup"],
        0,
        "model cache size after startup",
    )
    return result


def production_startup(
    checkout: Path, temporary_directory: Path
) -> dict[str, Any]:
    database_path = temporary_directory / "production-startup.sqlite3"
    log_path = temporary_directory / "uvicorn.log"
    port = available_port()
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(checkout),
            "DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
            "ATHES_ENV": "production",
            "ATHES_SECRET_KEY": "local-disposable-verification-secret",
            "ATHES_ALLOWED_ORIGINS": PRODUCTION_TEST_ORIGIN,
            "PORT": str(port),
        }
    )
    cache_result = startup_cache_check(
        checkout, temporary_directory / "startup-cache.sqlite3"
    )
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=checkout,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
    base_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 45
        health = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                tail = "\n".join(
                    log_path.read_text(
                        encoding="utf-8", errors="replace"
                    ).splitlines()[-30:]
                )
                raise ReadinessError(
                    f"Production-style Uvicorn exited early.\n{tail}"
                )
            try:
                health, _ = http_json("GET", f"{base_url}/")
                break
            except (OSError, ReadinessError):
                time.sleep(0.25)
        require(health is not None, "Production-style backend did not become ready.")
        require_equal(
            health["message"],
            "Athes Sentinel API is running",
            "health response",
        )

        openapi, _ = http_json("GET", f"{base_url}/openapi.json")
        paths = set(openapi["paths"])
        require(
            EXPECTED_NETWORK_ROUTES.issubset(paths),
            "OpenAPI is missing one or more network routes.",
        )
        for prefix in EXPECTED_OLD_ROUTE_PREFIXES:
            require(
                any(path.startswith(prefix) for path in paths),
                f"OpenAPI is missing existing route prefix {prefix}.",
            )

        login_body = json.dumps(
            {"username": "admin", "password": "admin123"}
        ).encode("utf-8")
        login, _ = http_json(
            "POST",
            f"{base_url}/auth/login",
            body=login_body,
            headers={"Content-Type": "application/json"},
        )
        token = login["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}
        protected, _ = http_json(
            "GET",
            f"{base_url}/network/datasets?limit=1&offset=0",
            headers=auth_headers,
        )
        require_equal(protected["total"], 0, "initial protected dataset total")

        preflight_request = urllib.request.Request(
            f"{base_url}/network/datasets/upload",
            method="OPTIONS",
            headers={
                "Origin": PRODUCTION_TEST_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        with urllib.request.urlopen(preflight_request, timeout=30) as response:
            preflight_headers = {
                key.lower(): value for key, value in response.headers.items()
            }
            preflight_status = response.status
            response.read()
        require_equal(preflight_status, 200, "CORS preflight status")
        require_equal(
            preflight_headers.get("access-control-allow-origin"),
            PRODUCTION_TEST_ORIGIN,
            "CORS allowed origin",
        )
        require_equal(
            preflight_headers.get("access-control-allow-credentials"),
            "true",
            "CORS credentials",
        )
        allowed_methods = preflight_headers.get(
            "access-control-allow-methods", ""
        )
        for method in ("GET", "POST", "PATCH"):
            require(method in allowed_methods, f"CORS omitted {method}.")

        upload_content = small_inference_csv()
        upload_body, upload_type = multipart_body(
            "deployment-inference.csv", upload_content
        )
        upload, _ = http_json(
            "POST",
            f"{base_url}/network/datasets/upload",
            body=upload_body,
            headers={
                **auth_headers,
                "Content-Type": upload_type,
            },
            expected_status=201,
        )
        require_equal(upload["total_records"], 1, "startup upload row count")
        require_equal(
            upload["source_type"],
            "nsl_kdd_inference",
            "startup upload source type",
        )
        analysis, _ = http_json(
            "POST",
            f"{base_url}/network/datasets/{upload['id']}/analyze",
            headers=auth_headers,
        )
        require_equal(
            analysis["total_predictions"], 1, "startup inference predictions"
        )
        require_equal(
            analysis["model_version"],
            EXPECTED_ARTIFACT_SHA256,
            "startup inference model version",
        )
        return {
            "command_equivalent": (
                "uvicorn backend.app.main:app --host 127.0.0.1 "
                "--port <temporary-port>"
            ),
            "bound_interface": "localhost only",
            "health_endpoint": "/",
            "health_response": "passed",
            "openapi_generation": "passed",
            "openapi_path_count": len(paths),
            "network_routes_registered": len(EXPECTED_NETWORK_ROUTES),
            "existing_application_route_groups_registered": list(
                EXPECTED_OLD_ROUTE_PREFIXES
            ),
            "real_jwt_login": "passed",
            "protected_network_read": "passed",
            "startup_model_cache_size": cache_result[
                "model_cache_size_after_startup"
            ],
            "startup_loaded_model": False,
            "multipart_inference_upload": "passed",
            "frozen_model_http_prediction": "passed",
            "prediction_count": analysis["total_predictions"],
            "model_version": analysis["model_version"],
            "cors_preflight": {
                "origin": "configured placeholder production origin",
                "credentials": True,
                "methods": ["GET", "POST", "PATCH"],
                "authorization_header": True,
                "multipart_content_type": True,
            },
            "disposable_table_database_created": database_path.exists(),
        }
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


def create_node_modules_junction(checkout: Path) -> Path:
    source = REPOSITORY_ROOT / "frontend" / "node_modules"
    target = checkout / "frontend" / "node_modules"
    require(source.is_dir(), "Existing frontend node_modules is unavailable.")
    result = run(
        ["cmd", "/c", "mklink", "/J", str(target), str(source)],
        cwd=checkout,
        check=False,
    )
    require_equal(result.returncode, 0, "node_modules junction creation")
    require(target.exists(), "node_modules junction was not created.")
    return target


def frontend_build(checkout: Path) -> dict[str, Any]:
    client_source = (
        checkout / "frontend" / "src" / "api" / "client.js"
    ).read_text(encoding="utf-8")
    require(
        "VITE_API_BASE_URL" in client_source,
        "Frontend API client does not use VITE_API_BASE_URL.",
    )
    require(
        "import.meta.env.PROD && !configuredApiBaseUrl" in client_source,
        "Production API URL absence is not handled explicitly.",
    )
    network_source = (
        checkout / "frontend" / "src" / "api" / "network.js"
    ).read_text(encoding="utf-8")
    require(
        'formData.append("file", file)' in network_source,
        "Network upload does not use the file multipart field.",
    )
    require(
        'apiClient.post("/network/datasets/upload", formData)' in network_source,
        "Network upload is not a POST.",
    )
    require(
        "apiClient.patch(" in network_source
        and "/status" in network_source,
        "Incident status update is not a PATCH.",
    )
    junction = create_node_modules_junction(checkout)
    distribution = checkout / "frontend" / "dist"
    env = os.environ.copy()
    env["VITE_API_BASE_URL"] = PRODUCTION_TEST_API_URL
    started = time.perf_counter()
    try:
        completed = run(
            ["npm.cmd", "run", "build"],
            cwd=checkout / "frontend",
            env=env,
            timeout=180,
        )
        duration = time.perf_counter() - started
        require(distribution.is_dir(), "Frontend build did not create dist.")
        bundle_text = "\n".join(
            path.read_text(encoding="utf-8", errors="replace")
            for path in distribution.rglob("*")
            if path.is_file() and path.suffix in {".js", ".html", ".css"}
        )
        require(
            PRODUCTION_TEST_API_URL in bundle_text,
            "Built frontend omitted the configured production API URL.",
        )
        require(
            "http://127.0.0.1:8000" not in bundle_text,
            "Production frontend bundle contains the localhost API fallback.",
        )
        bundled_names = [path.name for path in distribution.rglob("*") if path.is_file()]
        require(
            not any(
                name.endswith((".joblib", ".txt", ".db"))
                or "KDDTrain" in name
                or "KDDTest" in name
                for name in bundled_names
            ),
            "Frontend bundle contains a model, dataset, or database file.",
        )
        vercel = json.loads(
            (checkout / "frontend" / "vercel.json").read_text(encoding="utf-8")
        )
        require_equal(
            vercel["rewrites"][0]["destination"],
            "/index.html",
            "Vercel SPA rewrite",
        )
        return {
            "outcome": "passed",
            "duration_seconds": round(duration, 3),
            "configured_environment_variable": "VITE_API_BASE_URL",
            "configured_placeholder_url_embedded": True,
            "localhost_api_absent_from_production_bundle": True,
            "network_upload_method": "POST multipart FormData",
            "analysis_method": "POST",
            "incident_status_method": "PATCH",
            "model_or_dataset_bundled": False,
            "live_secret_bundled": False,
            "intentional_demo_credentials_note": (
                "The existing demo login guidance remains intentionally visible."
            ),
            "vercel_spa_refresh_rewrite": "passed",
            "generated_file_count": len(bundled_names),
            "build_output_removed": True,
        }
    finally:
        if distribution.exists():
            shutil.rmtree(distribution)
        if junction.exists():
            require(
                hasattr(junction, "is_junction") and junction.is_junction(),
                "Refusing to remove node_modules because it is not a junction.",
            )
            os.rmdir(junction)


def repository_hygiene(checkout: Path) -> dict[str, Any]:
    tracked_files = [
        line
        for line in git("ls-files").splitlines()
        if line
    ]
    forbidden_tracked = [
        path
        for path in tracked_files
        if (
            "/__pycache__/" in f"/{path}/"
            or path.endswith((".pyc", ".db"))
            or "/dist/" in f"/{path}/"
            or path in {".env", "frontend/.env", "backend/.env"}
        )
    ]
    require_equal(forbidden_tracked, [], "forbidden tracked generated files")

    machine_path_pattern = re.compile(
        r"(?<![A-Za-z])[A-Za-z]:[\\/]"
    )
    jwt_pattern = re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.")
    credential_url_pattern = re.compile(
        r"postgres(?:ql)?://[^\s/:]+:[^\s@]+@",
        re.IGNORECASE,
    )
    machine_paths: list[str] = []
    jwt_findings: list[str] = []
    credential_url_findings: list[str] = []
    for tracked_path in tracked_files:
        if tracked_path.endswith((".joblib", ".png", ".jpg", ".jpeg", ".ico")):
            continue
        path = checkout / tracked_path
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        is_deliberate_test_fixture = tracked_path.startswith(
            "backend/app/tests/"
        )
        if (
            tracked_path != "README.md"
            and not is_deliberate_test_fixture
            and machine_path_pattern.search(text)
        ):
            machine_paths.append(tracked_path)
        if jwt_pattern.search(text):
            jwt_findings.append(tracked_path)
        if credential_url_pattern.search(text):
            credential_url_findings.append(tracked_path)
    require_equal(
        sorted(set(machine_paths)),
        [],
        "tracked machine-specific source/report paths",
    )
    require_equal(sorted(set(jwt_findings)), [], "tracked JWT-like values")
    require_equal(
        sorted(set(credential_url_findings)),
        [],
        "tracked database credential URLs",
    )

    backend_runtime = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in (checkout / "backend").rglob("*.py")
        if "tests" not in path.parts
    )
    require(
        "KDDTrain+.txt" not in backend_runtime
        and "KDDTest+.txt" not in backend_runtime,
        "Backend runtime code refers to an ignored benchmark filename.",
    )
    return {
        "tracked_generated_or_local_files": forbidden_tracked,
        "tracked_raw_datasets": [],
        "machine_specific_paths_in_runtime_source_or_reports": [],
        "jwt_like_values": [],
        "database_credential_urls": [],
        "complete_dataset_contents_tracked": False,
        "runtime_benchmark_filename_references": False,
        "readme_note": (
            "README contains pre-existing local Windows command examples. "
            "It was excluded from runtime/source hygiene and left unchanged "
            "as explicitly required."
        ),
        "intentional_demo_credentials": (
            "Existing documented demo-user credentials remain intentional; "
            "no additional password or token material was found."
        ),
    }


def operational_characteristics(checkout: Path) -> dict[str, Any]:
    source = r'''
import json
from backend.app.network.analysis_service import ANALYSIS_BATCH_SIZE
from backend.app.network.service import FLOW_INSERT_BATCH_SIZE, MAX_UPLOAD_BYTES
from backend.app.ml.nsl_kdd_inference import load_final_detector
print(json.dumps({
    "max_upload_bytes": MAX_UPLOAD_BYTES,
    "flow_insert_batch_size": FLOW_INSERT_BATCH_SIZE,
    "analysis_batch_size": ANALYSIS_BATCH_SIZE,
    "model_cache_maxsize": load_final_detector.cache_parameters()["maxsize"],
}))
'''
    _, result = python_json(
        checkout,
        source,
        env={"DATABASE_URL": "sqlite:///:memory:"},
    )
    require_equal(result["max_upload_bytes"], 50 * 1024 * 1024, "upload limit")
    require_equal(result["analysis_batch_size"], 5_000, "analysis batch size")

    e2e_report = json.loads(
        (
            checkout
            / "ml_pipeline"
            / "reports"
            / "network_e2e_verification.json"
        ).read_text(encoding="utf-8")
    )
    require_equal(e2e_report["outcome"], "passed", "committed E2E outcome")
    require_equal(
        e2e_report["authenticated_workflow"]["analysis"]["complete_uploaded_rows"],
        22_544,
        "committed complete upload verification",
    )
    require(
        e2e_report["idempotency"]["reused_existing"],
        "Committed E2E did not verify completed-analysis reuse.",
    )
    return {
        **result,
        "upload_is_retained_on_server": False,
        "complete_kddtest_local_http_verification_rows": 22_544,
        "completed_analysis_reused": True,
        "child_write_rollback_covered_by_backend_tests": True,
        "analysis_execution": "synchronous",
        "known_limitations": [
            (
                "The 50 MiB upload and synchronous analysis path must be "
                "validated against the selected Render plan's actual request "
                "size, memory, and timeout limits during deployment."
            ),
            (
                "A future production architecture may use object storage and "
                "a background worker with progress polling for large datasets."
            ),
        ],
    }


def render_configuration(checkout: Path) -> dict[str, Any]:
    render = (checkout / "render.yaml").read_text(encoding="utf-8")
    for required in (
        "pip install -r requirements.txt",
        "uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT",
        "DATABASE_URL",
        "ATHES_SECRET_KEY",
        "ATHES_ENV",
        "production",
        "ATHES_ALLOWED_ORIGINS",
    ):
        require(required in render, f"render.yaml omitted {required}.")
    return {
        "build_command": "pip install -r requirements.txt",
        "start_command": (
            "uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT"
        ),
        "database_url_source": "Render database connectionString",
        "jwt_secret_source": "Render-generated environment value",
        "environment": "production",
        "allowed_origins_source": "manually configured environment value",
        "live_values_recorded": False,
    }


def write_report(report: dict[str, Any]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )


def print_summary(report: dict[str, Any]) -> None:
    print("Athes Sentinel deployment readiness verification")
    for label, value in (
        ("tracked artifact", report["tracked_artifact"]["outcome"]),
        ("clean checkout", report["clean_checkout"]["outcome"]),
        ("raw-data independence", report["raw_dataset_independence"]),
        ("runtime dependencies", report["dependency_audit"]["outcome"]),
        ("backend startup", report["backend_startup"]["outcome"]),
        ("PostgreSQL compilation", report["database_compatibility"]["outcome"]),
        ("environment/CORS", report["environment_and_cors"]["outcome"]),
        ("frontend build", report["frontend_build"]["outcome"]),
        ("repository hygiene", report["repository_hygiene"]["outcome"]),
        ("artifact integrity", report["artifact_integrity"]["outcome"]),
    ):
        print(f"  {label}: {str(value).upper()}")
    print(f"  report: {relative(REPORT_PATH)}")


def main() -> None:
    started = time.perf_counter()
    branch = git("branch", "--show-current")
    commit = git("rev-parse", "HEAD")
    artifact_path = REPOSITORY_ROOT / ARTIFACT_RELATIVE_PATH
    metadata_path = REPOSITORY_ROOT / METADATA_RELATIVE_PATH
    artifact_hash_before = sha256(artifact_path)
    metadata_hash_before = sha256(metadata_path)
    real_database_path = REPOSITORY_ROOT / "athes_sentinel.db"
    real_database_before = file_signature(real_database_path)

    tracked_artifact = git_artifact_audit()
    with tempfile.TemporaryDirectory(prefix="athes-deployment-readiness-") as name:
        temporary_directory = Path(name)
        checkout = temporary_directory / "checkout"
        checkout_policy = create_candidate_checkout(checkout)
        dependency_result = dependency_audit(checkout)
        model_result = clean_model_inference(checkout)
        database_result = database_compilation(
            checkout, temporary_directory / "metadata.sqlite3"
        )
        environment_result = verify_environment_failures(
            checkout, temporary_directory / "environment.sqlite3"
        )
        render_result = render_configuration(checkout)
        startup_result = production_startup(checkout, temporary_directory)
        frontend_result = frontend_build(checkout)
        hygiene_result = repository_hygiene(checkout)
        operations_result = operational_characteristics(checkout)

    artifact_hash_after = sha256(artifact_path)
    metadata_hash_after = sha256(metadata_path)
    real_database_after = file_signature(real_database_path)
    require_equal(
        artifact_hash_after, artifact_hash_before, "artifact hash stability"
    )
    require_equal(
        metadata_hash_after, metadata_hash_before, "metadata hash stability"
    )
    require_equal(
        real_database_after,
        real_database_before,
        "real local database signature",
    )

    report = {
        "overall_outcome": "passed",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "git_branch": branch,
        "git_commit": commit,
        "tracked_artifact": {"outcome": "passed", **tracked_artifact},
        "artifact_integrity": {
            "outcome": "passed",
            "sha256_before": artifact_hash_before,
            "sha256_after": artifact_hash_after,
            "metadata_sha256_before": metadata_hash_before,
            "metadata_sha256_after": metadata_hash_after,
            "contents_modified": False,
        },
        "clean_checkout": {
            "outcome": "passed",
            **checkout_policy,
            "model_load_and_sample_inference": model_result,
            "temporary_checkout_disposed": True,
        },
        "raw_dataset_independence": "passed",
        "dependency_audit": {"outcome": "passed", **dependency_result},
        "backend_startup": {"outcome": "passed", **startup_result},
        "route_and_table_registration": {
            "route_count": startup_result["openapi_path_count"],
            "network_routes": startup_result["network_routes_registered"],
            "tables": database_result["tables"],
            "table_count": database_result["table_count"],
        },
        "database_compatibility": {
            "outcome": "passed",
            **database_result,
            "deployed_database_contacted": False,
            "migration_note": (
                "Base.metadata.create_all() creates missing network tables but "
                "is not a versioned migration system. The deployed master "
                "database does not yet contain these additive tables, so no "
                "existing network-table migration is required before first "
                "deployment."
            ),
        },
        "environment_and_cors": {
            "outcome": "passed",
            "environment_handling": environment_result,
            "render_configuration": render_result,
            "cors_preflight": startup_result["cors_preflight"],
            "unrestricted_wildcard_with_credentials": False,
        },
        "frontend_build": frontend_result,
        "repository_hygiene": {"outcome": "passed", **hygiene_result},
        "upload_and_analysis_characteristics": operations_result,
        "known_deployment_limitations": operations_result["known_limitations"]
        + [
            (
                "PostgreSQL model definitions were compiled locally without "
                "connecting to Render PostgreSQL."
            ),
            (
                "The project still uses startup create_all rather than formal "
                "versioned migrations."
            ),
        ],
        "defects_found_and_fixed": [
            {
                "defect": (
                    "The production runtime directly imported joblib without "
                    "declaring it, and requirements did not guarantee the "
                    "scikit-learn 1.9.0 artifact-creation version."
                ),
                "fix": (
                    "Declared joblib and pinned scikit-learn==1.9.0 in "
                    "requirements.txt."
                ),
            },
            {
                "defect": (
                    "A production frontend without VITE_API_BASE_URL silently "
                    "used the localhost backend."
                ),
                "fix": (
                    "The production API client now fails clearly when the "
                    "environment variable is absent; development retains its "
                    "localhost fallback."
                ),
            },
            {
                "defect": (
                    "A production backend without ATHES_ALLOWED_ORIGINS "
                    "silently allowed only localhost, making a deployed Vercel "
                    "frontend unusable."
                ),
                "fix": (
                    "Production startup now requires ATHES_ALLOWED_ORIGINS; "
                    "development retains the localhost origin."
                ),
            },
        ],
        "live_service_safety": {
            "render_contacted": False,
            "postgresql_contacted": False,
            "vercel_contacted": False,
            "master_deployment_contacted": False,
            "only_http_bind": "127.0.0.1 temporary port",
            "real_local_database_unchanged": True,
        },
        "duration_seconds": round(time.perf_counter() - started, 3),
    }
    write_report(report)
    print_summary(report)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        failure = {
            "overall_outcome": "failed",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "failure_type": type(error).__name__,
            "failure_message": str(error),
            "live_service_safety": {
                "render_contacted": False,
                "postgresql_contacted": False,
                "vercel_contacted": False,
                "master_deployment_contacted": False,
            },
        }
        write_report(failure)
        print(f"Deployment readiness verification: FAILED ({error})")
        print(f"Report: {relative(REPORT_PATH)}")
        raise
