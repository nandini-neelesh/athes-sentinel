"""Parsing, validation, persistence, and read services for network datasets."""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import func, insert

from backend.app.database.network_models import (
    NetworkDataset,
    NetworkFlow,
    NetworkIncident,
    NetworkPrediction,
)
from ml_pipeline.attack_mapping import get_attack_family
from ml_pipeline.nsl_kdd_schema import (
    ALL_COLUMNS,
    CATEGORICAL_COLUMNS,
    DIFFICULTY_COLUMN,
    FEATURE_COLUMNS,
    LABEL_COLUMN,
    NUMERIC_FEATURE_COLUMNS,
)
from ml_pipeline.preprocessing import normalize_labels

LOGGER = logging.getLogger(__name__)
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
FLOW_INSERT_BATCH_SIZE = 2_000
SUPPORTED_EXTENSIONS = {".txt", ".csv"}
RATE_COLUMNS = [
    column for column in NUMERIC_FEATURE_COLUMNS if column.endswith("_rate")
]
INTEGER_FEATURE_COLUMNS = [
    column for column in NUMERIC_FEATURE_COLUMNS if column not in RATE_COLUMNS
]


class NetworkValidationError(ValueError):
    """Raised when an uploaded network dataset is invalid."""


class NetworkUploadTooLargeError(NetworkValidationError):
    """Raised when an upload exceeds the configured byte limit."""


class NetworkPersistenceError(RuntimeError):
    """Raised after a failed upload transaction has been rolled back."""


@dataclass
class ParsedNetworkDataset:
    """A fully validated upload ready for one persistence transaction."""

    dataframe: pd.DataFrame
    has_ground_truth: bool
    source_type: str
    label_distribution: list[dict[str, Any]]
    family_distribution: list[dict[str, Any]]
    protocol_distribution: list[dict[str, Any]]
    service_unique_count: int
    flag_distribution: list[dict[str, Any]]


def safe_filename(filename: str | None) -> str:
    """Store only a basename, never a client-supplied local path."""
    basename = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not basename:
        raise NetworkValidationError("Uploaded file must have a filename.")
    extension = Path(basename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise NetworkValidationError(
            "Unsupported file extension. Upload a .txt or .csv file."
        )
    return basename


def read_upload_bytes(file_bytes: bytes) -> str:
    """Enforce size/decoding rules and return UTF-8 text without a BOM."""
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise NetworkUploadTooLargeError(
            f"Upload exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit."
        )
    if not file_bytes:
        raise NetworkValidationError("Uploaded file is empty.")
    try:
        decoded = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise NetworkValidationError(
            "Uploaded file must be valid UTF-8 text."
        ) from error
    if not decoded.strip():
        raise NetworkValidationError("Uploaded file is empty.")
    return decoded


def _normalized_header_names(values: list[str]) -> list[str]:
    return [str(value).strip().lower() for value in values]


def _raise_invalid_header(normalized_header: list[str]) -> None:
    """Explain duplicate, missing, and extra attempted header fields."""
    duplicates = sorted(
        {
            column
            for column in normalized_header
            if normalized_header.count(column) > 1
        }
    )
    if duplicates:
        raise NetworkValidationError(
            f"Duplicate header names are not supported: {duplicates}."
        )

    expected = (
        ALL_COLUMNS
        if LABEL_COLUMN in normalized_header
        or DIFFICULTY_COLUMN in normalized_header
        else FEATURE_COLUMNS
    )
    expected_set = set(expected)
    actual_set = set(normalized_header)
    missing = [column for column in expected if column not in actual_set]
    extra = sorted(actual_set - expected_set)
    details = []
    if missing:
        details.append(f"missing columns: {missing}")
    if extra:
        details.append(f"unsupported extra columns: {extra}")
    if len(normalized_header) not in (len(FEATURE_COLUMNS), len(ALL_COLUMNS)):
        details.append(
            f"observed {len(normalized_header)} columns; expected 41 or 43"
        )
    raise NetworkValidationError(
        "Header must match exactly FEATURE_COLUMNS or ALL_COLUMNS; "
        + "; ".join(details or ["header is ambiguous or malformed"])
        + "."
    )


def parse_uploaded_dataframe(text: str) -> tuple[pd.DataFrame, bool]:
    """Detect an exact header or assign the official headerless schema."""
    try:
        first_row = next(csv.reader(io.StringIO(text), strict=True))
    except (StopIteration, csv.Error) as error:
        raise NetworkValidationError(
            "Uploaded file has no readable comma-separated rows."
        ) from error
    normalized_first_row = _normalized_header_names(first_row)
    official_names = set(ALL_COLUMNS)
    looks_like_header = bool(set(normalized_first_row) & official_names)
    exact_feature_header = (
        len(normalized_first_row) == len(FEATURE_COLUMNS)
        and set(normalized_first_row) == set(FEATURE_COLUMNS)
        and len(set(normalized_first_row)) == len(normalized_first_row)
    )
    exact_labelled_header = (
        len(normalized_first_row) == len(ALL_COLUMNS)
        and set(normalized_first_row) == set(ALL_COLUMNS)
        and len(set(normalized_first_row)) == len(normalized_first_row)
    )

    try:
        if exact_feature_header or exact_labelled_header:
            dataframe = pd.read_csv(io.StringIO(text), header=0)
            dataframe.columns = normalized_first_row
            expected = ALL_COLUMNS if exact_labelled_header else FEATURE_COLUMNS
            dataframe = dataframe.loc[:, expected]
            has_ground_truth = exact_labelled_header
        else:
            if looks_like_header:
                _raise_invalid_header(normalized_first_row)
            if len(first_row) not in (len(FEATURE_COLUMNS), len(ALL_COLUMNS)):
                raise NetworkValidationError(
                    "Headerless input must contain exactly 41 or 43 columns; "
                    f"observed {len(first_row)}."
                )
            dataframe = pd.read_csv(io.StringIO(text), header=None)
            if dataframe.shape[1] not in (
                len(FEATURE_COLUMNS),
                len(ALL_COLUMNS),
            ):
                raise NetworkValidationError(
                    "Input must contain exactly 41 or 43 columns; "
                    f"observed {dataframe.shape[1]}."
                )
            has_ground_truth = dataframe.shape[1] == len(ALL_COLUMNS)
            dataframe.columns = (
                ALL_COLUMNS if has_ground_truth else FEATURE_COLUMNS
            )
    except NetworkValidationError:
        raise
    except (pd.errors.ParserError, UnicodeError, ValueError) as error:
        raise NetworkValidationError(
            "Uploaded file is not a valid comma-separated NSL-KDD dataset."
        ) from error

    if dataframe.empty:
        raise NetworkValidationError(
            "Uploaded file must contain at least one data row."
        )
    if dataframe.columns.duplicated().any():
        duplicates = dataframe.columns[dataframe.columns.duplicated()].tolist()
        raise NetworkValidationError(
            f"Duplicate column names are not supported: {duplicates}."
        )
    expected_columns = ALL_COLUMNS if has_ground_truth else FEATURE_COLUMNS
    if list(dataframe.columns) != expected_columns:
        raise NetworkValidationError(
            "Parsed columns do not match the official NSL-KDD schema."
        )
    return dataframe, has_ground_truth


def _distribution(series: pd.Series) -> list[dict[str, Any]]:
    counts = series.value_counts()
    return [
        {"value": str(value), "count": int(count)}
        for value, count in counts.items()
    ]


def validate_uploaded_dataframe(
    dataframe: pd.DataFrame, has_ground_truth: bool
) -> ParsedNetworkDataset:
    """Validate and normalize every row before any database write."""
    cleaned = dataframe.copy(deep=True)
    missing_columns = [
        str(column)
        for column, count in cleaned.isna().sum().items()
        if int(count) > 0
    ]
    if missing_columns:
        raise NetworkValidationError(
            f"Missing values are not supported in columns: {missing_columns}."
        )

    for column in CATEGORICAL_COLUMNS:
        cleaned[column] = cleaned[column].astype(str).str.strip()
    blank_categorical = [
        column
        for column in CATEGORICAL_COLUMNS
        if cleaned[column].eq("").any()
    ]
    if blank_categorical:
        raise NetworkValidationError(
            "Blank categorical values are not supported in columns: "
            f"{blank_categorical}."
        )

    invalid_numeric_columns: list[str] = []
    for column in NUMERIC_FEATURE_COLUMNS:
        converted = pd.to_numeric(cleaned[column], errors="coerce")
        if converted.isna().any():
            invalid_numeric_columns.append(column)
        else:
            cleaned[column] = converted
    if invalid_numeric_columns:
        raise NetworkValidationError(
            "Invalid numeric values were found in columns: "
            f"{invalid_numeric_columns}."
        )

    numeric_values = cleaned[NUMERIC_FEATURE_COLUMNS].to_numpy(dtype=float)
    infinite_mask = np.isinf(numeric_values)
    if infinite_mask.any():
        infinite_columns = [
            column
            for column, has_infinity in zip(
                NUMERIC_FEATURE_COLUMNS, infinite_mask.any(axis=0)
            )
            if has_infinity
        ]
        raise NetworkValidationError(
            "Positive or negative infinity was found in columns: "
            f"{infinite_columns}."
        )

    non_integer_feature_columns = [
        column
        for column in INTEGER_FEATURE_COLUMNS
        if (cleaned[column] % 1 != 0).any()
    ]
    if non_integer_feature_columns:
        raise NetworkValidationError(
            "Integer-valued features contain fractional values in columns: "
            f"{non_integer_feature_columns}."
        )
    for column in INTEGER_FEATURE_COLUMNS:
        cleaned[column] = cleaned[column].astype("int64")
    for column in RATE_COLUMNS:
        cleaned[column] = cleaned[column].astype(float)

    label_distribution: list[dict[str, Any]] = []
    family_distribution: list[dict[str, Any]] = []
    if has_ground_truth:
        difficulty = pd.to_numeric(
            cleaned[DIFFICULTY_COLUMN], errors="coerce"
        )
        if difficulty.isna().any() or np.isinf(
            difficulty.to_numpy(dtype=float)
        ).any():
            raise NetworkValidationError(
                "difficulty_level must contain finite numeric whole numbers."
            )
        if (difficulty % 1 != 0).any():
            raise NetworkValidationError(
                "difficulty_level must contain whole numbers."
            )
        cleaned[DIFFICULTY_COLUMN] = difficulty.astype("int64")
        normalized = normalize_labels(cleaned[LABEL_COLUMN])
        families: list[str] = []
        for label in normalized:
            try:
                families.append(get_attack_family(label))
            except ValueError as error:
                raise NetworkValidationError(str(error)) from error
        cleaned[LABEL_COLUMN] = normalized
        cleaned["actual_family"] = families
        label_distribution = _distribution(normalized)
        family_distribution = _distribution(cleaned["actual_family"])

    return ParsedNetworkDataset(
        dataframe=cleaned,
        has_ground_truth=has_ground_truth,
        source_type=(
            "nsl_kdd_labelled"
            if has_ground_truth
            else "nsl_kdd_inference"
        ),
        label_distribution=label_distribution,
        family_distribution=family_distribution,
        protocol_distribution=_distribution(cleaned["protocol_type"]),
        service_unique_count=int(cleaned["service"].nunique()),
        flag_distribution=_distribution(cleaned["flag"]),
    )


def parse_and_validate_upload(
    filename: str | None, file_bytes: bytes
) -> tuple[str, ParsedNetworkDataset]:
    """Validate filename, size, decoding, structure, values, and labels."""
    stored_filename = safe_filename(filename)
    text = read_upload_bytes(file_bytes)
    dataframe, has_ground_truth = parse_uploaded_dataframe(text)
    return stored_filename, validate_uploaded_dataframe(
        dataframe, has_ground_truth
    )


def _execute_flow_batch(db, rows: list[dict[str, Any]]) -> None:
    """Execute one portable SQLAlchemy bulk insert batch."""
    db.execute(insert(NetworkFlow), rows)


def _flow_insert_rows(
    parsed: ParsedNetworkDataset,
    dataset_id: int,
    start: int,
    stop: int,
) -> list[dict[str, Any]]:
    """Build native-value mappings for one source-order batch."""
    frame = parsed.dataframe.iloc[start:stop]
    feature_records = frame.loc[:, FEATURE_COLUMNS].to_dict(orient="records")
    labels = (
        frame[LABEL_COLUMN].tolist() if parsed.has_ground_truth else []
    )
    families = (
        frame["actual_family"].tolist() if parsed.has_ground_truth else []
    )
    difficulties = (
        frame[DIFFICULTY_COLUMN].tolist()
        if parsed.has_ground_truth
        else []
    )
    rows: list[dict[str, Any]] = []
    for batch_index, feature_record in enumerate(feature_records):
        position = start + batch_index + 1
        row = {
            "dataset_id": dataset_id,
            "row_number": position,
            **feature_record,
            "actual_label": None,
            "actual_family": None,
            "difficulty_level": None,
        }
        if parsed.has_ground_truth:
            row.update(
                {
                    "actual_label": labels[batch_index],
                    "actual_family": families[batch_index],
                    "difficulty_level": int(difficulties[batch_index]),
                }
            )
        rows.append(row)
    return rows


def dataset_summary(dataset: NetworkDataset) -> dict[str, Any]:
    """Serialize shared dataset metadata without exposing ORM objects."""
    return {
        "id": dataset.id,
        "filename": dataset.filename,
        "uploaded_at": dataset.uploaded_at,
        "total_records": dataset.total_records,
        "has_ground_truth": dataset.has_ground_truth,
        "source_type": dataset.source_type,
        "analysis_status": dataset.analysis_status,
        "analysis_error": dataset.analysis_error,
        "model_name": dataset.model_name,
        "model_threshold": dataset.model_threshold,
        "analysis_started_at": dataset.analysis_started_at,
        "analysis_completed_at": dataset.analysis_completed_at,
    }


def ingest_network_dataset(
    db, filename: str | None, file_bytes: bytes
) -> dict[str, Any]:
    """Validate completely, then insert dataset and flows in one transaction."""
    stored_filename, parsed = parse_and_validate_upload(filename, file_bytes)
    row_count = int(len(parsed.dataframe))
    try:
        dataset = NetworkDataset(
            filename=stored_filename,
            total_records=row_count,
            has_ground_truth=parsed.has_ground_truth,
            source_type=parsed.source_type,
            analysis_status="uploaded",
            analysis_error=None,
            model_name=None,
            model_threshold=None,
            analysis_started_at=None,
            analysis_completed_at=None,
        )
        db.add(dataset)
        db.flush()
        for start in range(0, row_count, FLOW_INSERT_BATCH_SIZE):
            stop = min(start + FLOW_INSERT_BATCH_SIZE, row_count)
            rows = _flow_insert_rows(parsed, dataset.id, start, stop)
            _execute_flow_batch(db, rows)
        db.commit()
        db.refresh(dataset)
    except Exception as error:
        db.rollback()
        LOGGER.exception("Network dataset persistence failed")
        raise NetworkPersistenceError(
            "Network dataset could not be saved. No records were committed."
        ) from error

    return {
        **dataset_summary(dataset),
        "label_distribution": parsed.label_distribution,
        "attack_family_distribution": parsed.family_distribution,
        "protocol_distribution": parsed.protocol_distribution,
        "service_unique_count": parsed.service_unique_count,
        "flag_distribution": parsed.flag_distribution,
    }


def list_network_datasets(db, limit: int, offset: int) -> dict[str, Any]:
    """Return network datasets newest first with stable ID tie-breaking."""
    total = int(db.query(func.count(NetworkDataset.id)).scalar() or 0)
    datasets = (
        db.query(NetworkDataset)
        .order_by(NetworkDataset.uploaded_at.desc(), NetworkDataset.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "items": [dataset_summary(dataset) for dataset in datasets],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_network_dataset_detail(
    db, dataset_id: int
) -> dict[str, Any] | None:
    """Return dataset metadata and truthful current child/prediction counts."""
    dataset = db.get(NetworkDataset, dataset_id)
    if dataset is None:
        return None
    stored_flow_count = int(
        db.query(func.count(NetworkFlow.id))
        .filter(NetworkFlow.dataset_id == dataset_id)
        .scalar()
        or 0
    )
    prediction_count = int(
        db.query(func.count(NetworkPrediction.id))
        .filter(NetworkPrediction.dataset_id == dataset_id)
        .scalar()
        or 0
    )
    incident_count = int(
        db.query(func.count(NetworkIncident.id))
        .filter(NetworkIncident.dataset_id == dataset_id)
        .scalar()
        or 0
    )
    predicted_normal_count = int(
        db.query(func.count(NetworkPrediction.id))
        .filter(
            NetworkPrediction.dataset_id == dataset_id,
            NetworkPrediction.predicted_class == "normal",
        )
        .scalar()
        or 0
    )
    predicted_attack_count = int(
        db.query(func.count(NetworkPrediction.id))
        .filter(
            NetworkPrediction.dataset_id == dataset_id,
            NetworkPrediction.predicted_class == "attack",
        )
        .scalar()
        or 0
    )
    return {
        **dataset_summary(dataset),
        "stored_flow_count": stored_flow_count,
        "prediction_count": prediction_count,
        "incident_count": incident_count,
        "predicted_normal_count": predicted_normal_count,
        "predicted_attack_count": predicted_attack_count,
    }


def _serialize_flow(flow: NetworkFlow) -> dict[str, Any]:
    return {
        "id": flow.id,
        "dataset_id": flow.dataset_id,
        "row_number": flow.row_number,
        **{column: getattr(flow, column) for column in FEATURE_COLUMNS},
        "actual_label": flow.actual_label,
        "actual_family": flow.actual_family,
        "difficulty_level": flow.difficulty_level,
    }


def list_network_flows(
    db, dataset_id: int, limit: int, offset: int
) -> dict[str, Any] | None:
    """Return one source-ordered page, or None for an unknown dataset."""
    if db.get(NetworkDataset, dataset_id) is None:
        return None
    total = int(
        db.query(func.count(NetworkFlow.id))
        .filter(NetworkFlow.dataset_id == dataset_id)
        .scalar()
        or 0
    )
    flows = (
        db.query(NetworkFlow)
        .filter(NetworkFlow.dataset_id == dataset_id)
        .order_by(NetworkFlow.row_number.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "dataset_id": dataset_id,
        "items": [_serialize_flow(flow) for flow in flows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
