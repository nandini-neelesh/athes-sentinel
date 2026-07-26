"""Validated, lazy inference with the frozen NSL-KDD Random Forest pipeline."""

from __future__ import annotations

import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    fbeta_score,
    precision_score,
    recall_score,
)
from sklearn.pipeline import Pipeline
from sklearn.utils.validation import check_is_fitted

from ml_pipeline.nsl_kdd_schema import (
    ALL_COLUMNS,
    CATEGORICAL_COLUMNS,
    DIFFICULTY_COLUMN,
    FEATURE_COLUMNS,
    LABEL_COLUMN,
    NUMERIC_FEATURE_COLUMNS,
)
from ml_pipeline.preprocessing import normalize_labels

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FINAL_ARTIFACT_PATH = (
    REPOSITORY_ROOT
    / "ml_pipeline"
    / "artifacts"
    / "nsl_kdd_improved_binary_pipeline.joblib"
)
FINAL_METADATA_PATH = (
    REPOSITORY_ROOT
    / "ml_pipeline"
    / "artifacts"
    / "improved_model_metadata.json"
)
ATTACK_THRESHOLD = 0.38
CONSTANT_FEATURE_COLUMN = "num_outbound_cmds"
EXCLUDED_COLUMNS = [
    LABEL_COLUMN,
    DIFFICULTY_COLUMN,
    CONSTANT_FEATURE_COLUMN,
]
EXPECTED_MODEL_INPUT_COLUMNS = [
    column for column in FEATURE_COLUMNS if column != CONSTANT_FEATURE_COLUMN
]
CONTEXT_COLUMNS = [
    "protocol_type",
    "service",
    "flag",
    LABEL_COLUMN,
    DIFFICULTY_COLUMN,
]


class FinalDetectorError(RuntimeError):
    """Raised when the frozen model package cannot be loaded safely."""


class InputValidationError(ValueError):
    """Raised when inference data does not match a supported NSL-KDD format."""


def calculate_file_sha256(path: Path) -> str:
    """Calculate SHA-256 without loading the whole artifact into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for block in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@lru_cache(maxsize=1)
def load_final_detector() -> tuple[Pipeline, dict[str, Any]]:
    """Hash-check and lazily load the final detector once per process."""
    if not FINAL_ARTIFACT_PATH.is_file():
        raise FileNotFoundError(
            f"Final NSL-KDD model artifact not found: {FINAL_ARTIFACT_PATH}"
        )
    if not FINAL_METADATA_PATH.is_file():
        raise FileNotFoundError(
            f"Final NSL-KDD model metadata not found: {FINAL_METADATA_PATH}"
        )

    try:
        metadata = json.loads(FINAL_METADATA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FinalDetectorError(
            f"Could not read valid final model metadata: {FINAL_METADATA_PATH}"
        ) from error
    if not isinstance(metadata, dict):
        raise FinalDetectorError("Final model metadata must be a JSON object.")

    expected_hash = metadata.get("artifact_sha256")
    if not isinstance(expected_hash, str) or not expected_hash:
        raise FinalDetectorError("Final model metadata has no artifact SHA-256.")
    observed_hash = calculate_file_sha256(FINAL_ARTIFACT_PATH)
    if not secrets_equal(observed_hash, expected_hash):
        raise FinalDetectorError(
            "Final model artifact SHA-256 does not match metadata: "
            f"expected {expected_hash}, observed {observed_hash}."
        )

    try:
        metadata_threshold = float(metadata["selected_threshold"])
    except (KeyError, TypeError, ValueError) as error:
        raise FinalDetectorError(
            "Final model metadata has no valid selected threshold."
        ) from error
    if not math.isclose(
        metadata_threshold, ATTACK_THRESHOLD, rel_tol=0.0, abs_tol=1e-12
    ):
        raise FinalDetectorError(
            "Final model metadata threshold does not match the application "
            f"threshold: expected {ATTACK_THRESHOLD}, "
            f"observed {metadata_threshold}."
        )

    try:
        detector = joblib.load(FINAL_ARTIFACT_PATH)
    except Exception as error:
        raise FinalDetectorError(
            f"Could not load final model artifact: {FINAL_ARTIFACT_PATH}"
        ) from error
    if not isinstance(detector, Pipeline):
        raise FinalDetectorError(
            "Final model artifact is not a scikit-learn Pipeline."
        )
    required_steps = {"preprocessor", "classifier"}
    missing_steps = sorted(required_steps - set(detector.named_steps))
    if missing_steps:
        raise FinalDetectorError(
            f"Final model Pipeline is missing required steps: {missing_steps}."
        )
    try:
        check_is_fitted(detector)
        check_is_fitted(detector.named_steps["preprocessor"])
        check_is_fitted(detector.named_steps["classifier"])
    except Exception as error:
        raise FinalDetectorError(
            "Final model Pipeline or one of its required steps is not fitted."
        ) from error
    if not callable(
        getattr(detector.named_steps["classifier"], "predict_proba", None)
    ):
        raise FinalDetectorError(
            "Final model classifier does not support predict_proba."
        )

    return detector, metadata


def secrets_equal(observed: str, expected: str) -> bool:
    """Compare hexadecimal hashes without leaking mismatch position."""
    return hashlib.sha256(observed.encode()).digest() == hashlib.sha256(
        expected.lower().encode()
    ).digest()


def _validate_supported_structure(dataframe: pd.DataFrame) -> None:
    """Require exactly the official 41- or 43-column input structure."""
    duplicated = dataframe.columns[dataframe.columns.duplicated()].tolist()
    if duplicated:
        raise InputValidationError(
            f"Duplicate column names are not supported: {duplicated}."
        )

    actual_columns = set(dataframe.columns)
    feature_columns = set(FEATURE_COLUMNS)
    all_columns = set(ALL_COLUMNS)
    if actual_columns in (feature_columns, all_columns):
        return

    missing_features = [
        column for column in FEATURE_COLUMNS if column not in actual_columns
    ]
    unsupported_columns = sorted(
        str(column) for column in actual_columns - all_columns
    )
    messages: list[str] = []
    if missing_features:
        messages.append(f"missing required feature columns: {missing_features}")
    if unsupported_columns:
        messages.append(f"unsupported extra columns: {unsupported_columns}")
    supplied_context = actual_columns & {LABEL_COLUMN, DIFFICULTY_COLUMN}
    if not missing_features and not unsupported_columns and supplied_context:
        messages.append(
            "label and difficulty_level must either both be supplied or both "
            "be omitted"
        )
    detail = "; ".join(messages) or "column structure is unsupported"
    raise InputValidationError(
        "Expected exactly the official 41 feature columns or all 43 labelled "
        f"NSL-KDD columns; {detail}."
    )


def prepare_features_for_inference(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Validate input and return the exact 40 trained feature columns."""
    if not isinstance(dataframe, pd.DataFrame):
        raise TypeError("Inference input must be a pandas DataFrame.")
    if dataframe.empty:
        raise InputValidationError("Inference input must contain at least one row.")
    _validate_supported_structure(dataframe)

    # Work on a deep copy so validation and coercion never alter caller data.
    working = dataframe.copy(deep=True)
    missing_counts = working.isna().sum()
    missing_columns = [
        str(column)
        for column, count in missing_counts.items()
        if int(count) > 0
    ]
    if missing_columns:
        raise InputValidationError(
            f"Missing values are not supported in columns: {missing_columns}."
        )

    for column in CATEGORICAL_COLUMNS:
        working[column] = working[column].astype(str).str.strip()

    invalid_numeric_columns: list[str] = []
    for column in NUMERIC_FEATURE_COLUMNS:
        converted = pd.to_numeric(working[column], errors="coerce")
        if converted.isna().any():
            invalid_numeric_columns.append(column)
        else:
            working[column] = converted
    if invalid_numeric_columns:
        raise InputValidationError(
            "Invalid numeric values were found in columns: "
            f"{invalid_numeric_columns}."
        )

    numeric_values = working[NUMERIC_FEATURE_COLUMNS].to_numpy(dtype=float)
    infinite_mask = np.isinf(numeric_values)
    if infinite_mask.any():
        infinite_columns = [
            column
            for column, has_infinity in zip(
                NUMERIC_FEATURE_COLUMNS, infinite_mask.any(axis=0)
            )
            if has_infinity
        ]
        raise InputValidationError(
            "Positive or negative infinity was found in columns: "
            f"{infinite_columns}."
        )

    prepared = working.loc[:, EXPECTED_MODEL_INPUT_COLUMNS].copy()
    if list(prepared.columns) != EXPECTED_MODEL_INPUT_COLUMNS:
        raise InputValidationError(
            "Prepared features do not match the trained 40-column order."
        )
    return prepared


def predict_network_flows(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Predict attack probability and the frozen-threshold binary outcome."""
    prepared = prepare_features_for_inference(dataframe)
    detector, _ = load_final_detector()
    classifier = detector.named_steps["classifier"]
    class_positions = np.flatnonzero(classifier.classes_ == 1)
    if len(class_positions) != 1:
        raise FinalDetectorError(
            "Final classifier does not contain one unique attack class 1."
        )
    probabilities = np.asarray(
        detector.predict_proba(prepared)[:, int(class_positions[0])],
        dtype=float,
    )
    predicted_binary = (probabilities >= ATTACK_THRESHOLD).astype("int8")

    result = pd.DataFrame(index=dataframe.index.copy())
    for column in ["protocol_type", "service", "flag"]:
        result[column] = prepared[column].to_numpy(copy=True)
    for column in [LABEL_COLUMN, DIFFICULTY_COLUMN]:
        if column in dataframe.columns:
            result[column] = dataframe[column].to_numpy(copy=True)
    result["rf_attack_probability"] = probabilities
    result["predicted_binary"] = predicted_binary
    result["predicted_class"] = np.where(
        predicted_binary == 1, "attack", "normal"
    )
    return result


def summarize_predictions(predictions: pd.DataFrame) -> dict[str, Any]:
    """Summarize predictions and optional labelled benchmark outcomes."""
    required_columns = {
        "rf_attack_probability",
        "predicted_binary",
        "predicted_class",
    }
    missing = sorted(required_columns - set(predictions.columns))
    if missing:
        raise InputValidationError(
            f"Prediction output is missing required columns: {missing}."
        )
    if predictions.empty:
        raise InputValidationError("Prediction output must contain at least one row.")

    probabilities = pd.to_numeric(
        predictions["rf_attack_probability"], errors="raise"
    )
    predicted_binary = pd.to_numeric(
        predictions["predicted_binary"], errors="raise"
    ).astype(int)
    total = int(len(predictions))
    predicted_attack = int((predicted_binary == 1).sum())
    predicted_normal = total - predicted_attack
    summary: dict[str, Any] = {
        "prediction_data": {
            "total_records": total,
            "predicted_normal": predicted_normal,
            "predicted_attack": predicted_attack,
            "predicted_attack_percentage": (
                float(predicted_attack / total * 100)
            ),
            "minimum_probability": float(probabilities.min()),
            "maximum_probability": float(probabilities.max()),
            "mean_probability": float(probabilities.mean()),
            "threshold_used": ATTACK_THRESHOLD,
        }
    }

    if LABEL_COLUMN in predictions.columns:
        actual_binary = (
            normalize_labels(predictions[LABEL_COLUMN])
            .ne("normal")
            .astype("int8")
        )
        true_negatives = int(
            ((actual_binary == 0) & (predicted_binary == 0)).sum()
        )
        false_positives = int(
            ((actual_binary == 0) & (predicted_binary == 1)).sum()
        )
        false_negatives = int(
            ((actual_binary == 1) & (predicted_binary == 0)).sum()
        )
        true_positives = int(
            ((actual_binary == 1) & (predicted_binary == 1)).sum()
        )
        actual_normal = int((actual_binary == 0).sum())
        actual_attack = total - actual_normal
        summary["benchmark_ground_truth"] = {
            "actual_normal": actual_normal,
            "actual_attack": actual_attack,
            "true_negatives": true_negatives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "true_positives": true_positives,
            "accuracy": float(
                accuracy_score(actual_binary, predicted_binary)
            ),
            "precision": float(
                precision_score(
                    actual_binary, predicted_binary, zero_division=0
                )
            ),
            "recall": float(
                recall_score(actual_binary, predicted_binary, zero_division=0)
            ),
            "f1": float(
                f1_score(actual_binary, predicted_binary, zero_division=0)
            ),
            "f2": float(
                fbeta_score(
                    actual_binary,
                    predicted_binary,
                    beta=2,
                    zero_division=0,
                )
            ),
            "false_positive_rate": (
                float(false_positives / actual_normal)
                if actual_normal
                else 0.0
            ),
            "false_negative_rate": (
                float(false_negatives / actual_attack)
                if actual_attack
                else 0.0
            ),
        }
    return summary
