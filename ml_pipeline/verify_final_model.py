"""Verify the frozen final detector through the application inference module."""

from __future__ import annotations

import json
import platform
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from backend.app.ml.nsl_kdd_inference import (
    ATTACK_THRESHOLD,
    FINAL_ARTIFACT_PATH,
    FINAL_METADATA_PATH,
    InputValidationError,
    calculate_file_sha256,
    load_final_detector,
    predict_network_flows,
    prepare_features_for_inference,
    summarize_predictions,
)
from ml_pipeline.nsl_kdd_schema import FEATURE_COLUMNS
from ml_pipeline.preprocessing import load_complete_nsl_kdd

TEST_FILENAME = "KDDTest+.txt"
METRIC_TOLERANCE = 1e-9
EXPECTED_TEST_ROWS = 22_544


def repository_root() -> Path:
    """Resolve the repository root safely from this script."""
    return Path(__file__).resolve().parent.parent


def expect_validation_error(
    case_name: str,
    operation: Callable[[], Any],
    expected_text: str,
    results: dict[str, str],
) -> None:
    """Require one validation case to fail clearly for the expected reason."""
    try:
        operation()
    except InputValidationError as error:
        if expected_text.lower() not in str(error).lower():
            raise AssertionError(
                f"{case_name} raised the wrong validation message: {error}"
            ) from error
        results[case_name] = "passed"
        return
    raise AssertionError(f"{case_name} did not raise InputValidationError.")


def run_validation_smoke_tests(test: pd.DataFrame) -> dict[str, str]:
    """Exercise supported formats and required validation failures in memory."""
    results: dict[str, str] = {}
    valid_43 = test.iloc[:2].copy(deep=True)
    original_43 = valid_43.copy(deep=True)
    prepared_43 = prepare_features_for_inference(valid_43)
    if prepared_43.shape != (2, 40):
        raise AssertionError("Valid 43-column input did not produce 40 features.")
    pd.testing.assert_frame_equal(valid_43, original_43)
    results["valid_43_column_input"] = "passed"
    results["caller_dataframe_not_modified"] = "passed"

    valid_41 = valid_43.loc[:, FEATURE_COLUMNS].copy()
    prepared_41 = prepare_features_for_inference(valid_41)
    if prepared_41.shape != (2, 40):
        raise AssertionError("Valid 41-column input did not produce 40 features.")
    results["valid_41_column_input"] = "passed"

    missing_column = valid_41.drop(columns=["duration"])
    expect_validation_error(
        "missing_required_column",
        lambda: prepare_features_for_inference(missing_column),
        "duration",
        results,
    )

    extra_column = valid_41.assign(unsupported_extra=1)
    expect_validation_error(
        "unsupported_extra_column",
        lambda: prepare_features_for_inference(extra_column),
        "unsupported_extra",
        results,
    )

    invalid_numeric = valid_41.copy()
    invalid_numeric["duration"] = invalid_numeric["duration"].astype(object)
    invalid_numeric.iloc[0, invalid_numeric.columns.get_loc("duration")] = (
        "not-a-number"
    )
    expect_validation_error(
        "invalid_numeric_value",
        lambda: prepare_features_for_inference(invalid_numeric),
        "duration",
        results,
    )

    missing_value = valid_41.copy()
    missing_value.iloc[0, missing_value.columns.get_loc("service")] = np.nan
    expect_validation_error(
        "missing_value",
        lambda: prepare_features_for_inference(missing_value),
        "service",
        results,
    )

    infinite_value = valid_41.copy()
    infinite_value["duration"] = infinite_value["duration"].astype(float)
    infinite_value.iloc[0, infinite_value.columns.get_loc("duration")] = np.inf
    expect_validation_error(
        "infinite_value",
        lambda: prepare_features_for_inference(infinite_value),
        "infinity",
        results,
    )
    return results


def predict_with_fit_guard(test: pd.DataFrame) -> pd.DataFrame:
    """Fail immediately if inference calls a relevant fitting method."""

    def fitting_forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("A fitting method was called during inference.")

    guarded_methods = [
        (Pipeline, "fit"),
        (ColumnTransformer, "fit"),
        (ColumnTransformer, "fit_transform"),
        (OneHotEncoder, "fit"),
        (OneHotEncoder, "fit_transform"),
        (RandomForestClassifier, "fit"),
    ]
    with ExitStack() as stack:
        for class_type, method_name in guarded_methods:
            stack.enter_context(
                patch.object(class_type, method_name, new=fitting_forbidden)
            )
        return predict_network_flows(test)


def compare_metrics(
    reproduced: dict[str, Any], expected: dict[str, Any]
) -> tuple[dict[str, float], float]:
    """Require reproduced N2.1 metrics to match within the fixed tolerance."""
    expected_matrix = expected["confusion_matrix"]
    pairs = {
        "accuracy": (
            float(reproduced["accuracy"]),
            float(expected["accuracy"]),
        ),
        "precision": (
            float(reproduced["precision"]),
            float(expected["precision"]),
        ),
        "recall": (
            float(reproduced["recall"]),
            float(expected["recall"]),
        ),
        "f1": (float(reproduced["f1"]), float(expected["f1"])),
        "f2": (float(reproduced["f2"]), float(expected["f2"])),
        "false_positive_rate": (
            float(reproduced["false_positive_rate"]),
            float(expected["false_positive_rate"]),
        ),
        "false_negative_rate": (
            float(reproduced["false_negative_rate"]),
            float(expected["false_negative_rate"]),
        ),
        "true_negatives": (
            float(reproduced["true_negatives"]),
            float(expected_matrix["true_negatives"]),
        ),
        "false_positives": (
            float(reproduced["false_positives"]),
            float(expected_matrix["false_positives"]),
        ),
        "false_negatives": (
            float(reproduced["false_negatives"]),
            float(expected_matrix["false_negatives"]),
        ),
        "true_positives": (
            float(reproduced["true_positives"]),
            float(expected_matrix["true_positives"]),
        ),
    }
    differences = {
        name: abs(observed - stored)
        for name, (observed, stored) in pairs.items()
    }
    failures = {
        name: difference
        for name, difference in differences.items()
        if difference > METRIC_TOLERANCE
    }
    if failures:
        raise AssertionError(
            "Final model predictions differ from stored N2.1 metrics: "
            f"{failures}"
        )
    return differences, max(differences.values(), default=0.0)


def write_json(path: Path, content: dict[str, Any]) -> None:
    """Write a human-readable UTF-8 JSON report."""
    path.write_text(json.dumps(content, indent=2), encoding="utf-8")


def main() -> None:
    """Run package, inference, metric, cache, and validation verification."""
    root = repository_root()
    test_path = root / "data" / "external" / "nsl-kdd" / TEST_FILENAME
    expected_metrics_path = (
        root / "ml_pipeline" / "reports" / "improved_binary_metrics.json"
    )
    report_path = (
        root / "ml_pipeline" / "reports" / "final_model_verification.json"
    )

    load_final_detector.cache_clear()
    first_detector, metadata = load_final_detector()
    second_detector, second_metadata = load_final_detector()
    cache_verified = (
        first_detector is second_detector and metadata is second_metadata
    )
    if not cache_verified:
        raise AssertionError("Cached loading did not return the same objects.")

    observed_hash = calculate_file_sha256(FINAL_ARTIFACT_PATH)
    expected_hash = str(metadata["artifact_sha256"]).lower()
    hash_verified = observed_hash == expected_hash
    if not hash_verified:
        raise AssertionError("Artifact hash verification failed.")
    if float(metadata["selected_threshold"]) != ATTACK_THRESHOLD:
        raise AssertionError("Metadata threshold does not equal 0.38.")

    test = load_complete_nsl_kdd(test_path)
    if len(test) != EXPECTED_TEST_ROWS:
        raise AssertionError(
            f"Expected {EXPECTED_TEST_ROWS} test rows, observed {len(test)}."
        )
    validation_results = run_validation_smoke_tests(test)
    predictions = predict_with_fit_guard(test)
    if len(predictions) != EXPECTED_TEST_ROWS:
        raise AssertionError(
            f"Expected {EXPECTED_TEST_ROWS} predictions, "
            f"observed {len(predictions)}."
        )
    probabilities = predictions["rf_attack_probability"]
    if not probabilities.between(0.0, 1.0, inclusive="both").all():
        raise AssertionError("One or more predicted probabilities are outside [0, 1].")
    predicted_classes = set(predictions["predicted_class"].unique())
    if not predicted_classes <= {"normal", "attack"}:
        raise AssertionError(
            f"Unexpected predicted classes were returned: {predicted_classes}."
        )

    summary = summarize_predictions(predictions)
    prediction_data = summary["prediction_data"]
    reproduced = summary["benchmark_ground_truth"]
    if prediction_data["threshold_used"] != ATTACK_THRESHOLD:
        raise AssertionError("Prediction summary did not use threshold 0.38.")

    expected_report = json.loads(
        expected_metrics_path.read_text(encoding="utf-8")
    )
    expected = expected_report["official_test_metrics_selected_threshold"]
    differences, maximum_difference = compare_metrics(reproduced, expected)

    classifier = first_detector.named_steps["classifier"]
    report = {
        "verification_outcome": "passed",
        "artifact_relative_path": FINAL_ARTIFACT_PATH.relative_to(root).as_posix(),
        "metadata_relative_path": FINAL_METADATA_PATH.relative_to(root).as_posix(),
        "artifact_size_bytes": FINAL_ARTIFACT_PATH.stat().st_size,
        "artifact_sha256": observed_hash,
        "artifact_hash_matches_metadata": hash_verified,
        "model_type": (
            f"{type(first_detector).__module__}."
            f"{type(first_detector).__name__}"
        ),
        "classifier_type": (
            f"{type(classifier).__module__}.{type(classifier).__name__}"
        ),
        "threshold": ATTACK_THRESHOLD,
        "official_test_row_count": int(len(test)),
        "prediction_counts": {
            "normal": prediction_data["predicted_normal"],
            "attack": prediction_data["predicted_attack"],
        },
        "reproduced_metrics": reproduced,
        "expected_metrics": {
            "accuracy": expected["accuracy"],
            "precision": expected["precision"],
            "recall": expected["recall"],
            "f1": expected["f1"],
            "f2": expected["f2"],
            "false_positive_rate": expected["false_positive_rate"],
            "false_negative_rate": expected["false_negative_rate"],
            "true_negatives": expected["confusion_matrix"]["true_negatives"],
            "false_positives": expected["confusion_matrix"]["false_positives"],
            "false_negatives": expected["confusion_matrix"]["false_negatives"],
            "true_positives": expected["confusion_matrix"]["true_positives"],
        },
        "metric_absolute_differences": differences,
        "metric_tolerance": METRIC_TOLERANCE,
        "maximum_metric_difference": maximum_difference,
        "cache_verification": {
            "passed": cache_verified,
            "same_pipeline_object": first_detector is second_detector,
            "same_metadata_object": metadata is second_metadata,
            "cache_maxsize": 1,
        },
        "supported_input_formats": {
            "labelled_official": "all 43 official NSL-KDD columns",
            "inference_only": "exactly the 41 official feature columns",
            "model_input_after_validation": (
                "40 columns after dropping num_outbound_cmds"
            ),
        },
        "validation_cases_tested": validation_results,
        "fitting_guard": {
            "passed": True,
            "fit_methods_called": False,
            "guarded_methods": [
                "Pipeline.fit",
                "ColumnTransformer.fit",
                "ColumnTransformer.fit_transform",
                "OneHotEncoder.fit",
                "OneHotEncoder.fit_transform",
                "RandomForestClassifier.fit",
            ],
        },
        "no_model_training_or_fitting_occurred": True,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "package_versions": {
            "python": platform.python_version(),
            "scikit_learn": sklearn.__version__,
            "joblib": joblib.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
    }
    write_json(report_path, report)

    print(f"Artifact hash verified: {hash_verified} ({observed_hash})")
    print(
        "Loaded types: "
        f"{type(first_detector).__name__}/"
        f"{type(classifier).__name__}"
    )
    print(f"Threshold: {ATTACK_THRESHOLD}")
    print(f"Complete official test rows: {len(test)}")
    print(
        "Predicted normal/attack: "
        f"{prediction_data['predicted_normal']}/"
        f"{prediction_data['predicted_attack']}"
    )
    print(
        "Confusion matrix (TN, FP, FN, TP): "
        f"{reproduced['true_negatives']}, "
        f"{reproduced['false_positives']}, "
        f"{reproduced['false_negatives']}, "
        f"{reproduced['true_positives']}"
    )
    print(f"Precision: {reproduced['precision']:.12f}")
    print(f"Recall: {reproduced['recall']:.12f}")
    print(f"F1: {reproduced['f1']:.12f}")
    print(f"F2: {reproduced['f2']:.12f}")
    print(
        "False-positive rate: "
        f"{reproduced['false_positive_rate']:.12f}"
    )
    print(f"Maximum stored-metric difference: {maximum_difference:.12g}")
    print(f"Cache verification: {cache_verified}")
    print(f"Validation smoke tests: {validation_results}")
    print("Fit-method guard: passed; no fitting methods were called")
    print(f"Verification report: {report_path}")


if __name__ == "__main__":
    main()
