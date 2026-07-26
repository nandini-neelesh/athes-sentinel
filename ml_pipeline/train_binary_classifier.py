"""Train and evaluate a transparent binary Random Forest NSL-KDD baseline."""

from __future__ import annotations

import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

import joblib
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline

from ml_pipeline.attack_mapping import get_attack_family
from ml_pipeline.nsl_kdd_schema import CATEGORICAL_COLUMNS, LABEL_COLUMN
from ml_pipeline.preprocessing import (
    EXCLUDED_COLUMNS,
    INCLUDED_FEATURE_COLUMNS,
    build_preprocessor,
    load_complete_nsl_kdd,
    normalize_labels,
    split_features_and_target,
)

DATASET_DIRECTORY = Path("data") / "external" / "nsl-kdd"
TRAIN_FILENAME = "KDDTrain+.txt"
TEST_FILENAME = "KDDTest+.txt"
MODEL_FILENAME = "nsl_kdd_binary_pipeline.joblib"
DEFAULT_THRESHOLD = 0.5

# These fixed values are reasonable baseline choices, not claimed optimal values.
MODEL_PARAMETERS = {
    "n_estimators": 200,
    "max_depth": 25,
    "min_samples_leaf": 2,
    "class_weight": "balanced_subsample",
    "random_state": 42,
    "n_jobs": -1,
}


def repository_root() -> Path:
    """Resolve the repository root from this script rather than the working dir."""
    return Path(__file__).resolve().parent.parent


def validate_label_mapping(train: pd.DataFrame, test: pd.DataFrame) -> list[str]:
    """Fail before training if any normalized train or test label is unmapped."""
    all_labels = sorted(
        set(normalize_labels(train[LABEL_COLUMN]))
        | set(normalize_labels(test[LABEL_COLUMN]))
    )
    for label in all_labels:
        get_attack_family(label)
    return all_labels


def safe_rate(numerator: int, denominator: int) -> float:
    """Calculate a rate safely when a denominator could be zero."""
    return float(numerator / denominator) if denominator else 0.0


def calculate_metrics(
    y_test: pd.Series,
    predictions: Any,
    attack_probabilities: Any,
) -> tuple[dict[str, Any], list[list[int]]]:
    """Calculate binary metrics with attack as the positive class."""
    matrix = confusion_matrix(y_test, predictions, labels=[0, 1])
    true_negatives, false_positives, false_negatives, true_positives = (
        int(value) for value in matrix.ravel()
    )
    metrics = {
        "accuracy": float(accuracy_score(y_test, predictions)),
        "balanced_accuracy": float(
            balanced_accuracy_score(y_test, predictions)
        ),
        "precision": float(
            precision_score(y_test, predictions, pos_label=1, zero_division=0)
        ),
        "recall": float(
            recall_score(y_test, predictions, pos_label=1, zero_division=0)
        ),
        "f1_score": float(
            f1_score(y_test, predictions, pos_label=1, zero_division=0)
        ),
        "roc_auc": float(roc_auc_score(y_test, attack_probabilities)),
        "average_precision_pr_auc": float(
            average_precision_score(y_test, attack_probabilities)
        ),
        "confusion_matrix": {
            "true_negatives": true_negatives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "true_positives": true_positives,
        },
        "false_positive_rate": safe_rate(
            false_positives, false_positives + true_negatives
        ),
        "false_negative_rate": safe_rate(
            false_negatives, false_negatives + true_positives
        ),
        "specificity_true_negative_rate": safe_rate(
            true_negatives, true_negatives + false_positives
        ),
    }
    return metrics, matrix.astype(int).tolist()


def build_family_report(
    test: pd.DataFrame, predictions: Any
) -> pd.DataFrame:
    """Summarize binary detection outcomes for each real attack family."""
    normalized = normalize_labels(test[LABEL_COLUMN])
    families = normalized.map(get_attack_family)
    prediction_series = pd.Series(predictions, index=test.index)
    rows: list[dict[str, Any]] = []

    for family in ["dos", "probe", "r2l", "u2r"]:
        family_predictions = prediction_series[families == family]
        total = int(len(family_predictions))
        predicted_attack = int((family_predictions == 1).sum())
        missed_normal = int((family_predictions == 0).sum())
        rows.append(
            {
                "family": family,
                "total_test_records": total,
                "predicted_as_attack": predicted_attack,
                "missed_as_normal": missed_normal,
                "detection_recall": safe_rate(predicted_attack, total),
                "correctly_predicted_normal": None,
                "falsely_flagged_attack": None,
                "false_positive_rate": None,
            }
        )

    normal_predictions = prediction_series[families == "normal"]
    normal_total = int(len(normal_predictions))
    correctly_normal = int((normal_predictions == 0).sum())
    falsely_flagged = int((normal_predictions == 1).sum())
    rows.append(
        {
            "family": "normal",
            "total_test_records": normal_total,
            "predicted_as_attack": None,
            "missed_as_normal": None,
            "detection_recall": None,
            "correctly_predicted_normal": correctly_normal,
            "falsely_flagged_attack": falsely_flagged,
            "false_positive_rate": safe_rate(falsely_flagged, normal_total),
        }
    )
    return pd.DataFrame(rows)


def sha256_file(path: Path) -> str:
    """Hash an artifact without loading the entire file into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for block in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative_path(path: Path, root: Path) -> str:
    """Return a portable repository-relative path for saved metadata."""
    return path.relative_to(root).as_posix()


def write_json(path: Path, content: dict[str, Any]) -> None:
    """Write a human-readable UTF-8 JSON report."""
    path.write_text(json.dumps(content, indent=2), encoding="utf-8")


def print_summary(
    train_shape: tuple[int, int],
    test_shape: tuple[int, int],
    transformed_feature_count: int,
    metrics_report: dict[str, Any],
    family_report: pd.DataFrame,
    artifact_path: Path,
    report_paths: list[Path],
) -> None:
    """Print the key outcomes without dumping full data structures."""
    metrics = metrics_report["test_metrics"]
    timing = metrics_report["timing_seconds"]
    matrix = metrics["confusion_matrix"]
    print(f"Complete train shape: {train_shape}")
    print(f"Complete test shape: {test_shape}")
    print(f"Selected features before encoding: {len(INCLUDED_FEATURE_COLUMNS)}")
    print(f"Transformed features after encoding: {transformed_feature_count}")
    print(f"Training time (seconds): {timing['training']:.3f}")
    print(f"Prediction time (seconds): {timing['prediction']:.3f}")
    print(
        "Confusion matrix (TN, FP, FN, TP): "
        f"{matrix['true_negatives']}, {matrix['false_positives']}, "
        f"{matrix['false_negatives']}, {matrix['true_positives']}"
    )
    print(f"Precision: {metrics['precision']:.6f}")
    print(f"Recall: {metrics['recall']:.6f}")
    print(f"F1: {metrics['f1_score']:.6f}")
    print(f"ROC-AUC: {metrics['roc_auc']:.6f}")
    print(f"PR-AUC: {metrics['average_precision_pr_auc']:.6f}")
    print(f"False-positive rate: {metrics['false_positive_rate']:.6f}")
    print("Family-level detection recall:")
    for row in family_report.itertuples(index=False):
        if row.family != "normal":
            print(f"  {row.family}: {row.detection_recall:.6f}")
    print(f"Artifact: {artifact_path} ({artifact_path.stat().st_size} bytes)")
    print("Generated reports:")
    for path in report_paths:
        print(f"  {path}")


def main() -> None:
    """Run one fixed train-only fit and one complete official-test evaluation."""
    root = repository_root()
    train_path = root / DATASET_DIRECTORY / TRAIN_FILENAME
    test_path = root / DATASET_DIRECTORY / TEST_FILENAME
    reports_directory = root / "ml_pipeline" / "reports"
    artifacts_directory = root / "ml_pipeline" / "artifacts"
    reports_directory.mkdir(parents=True, exist_ok=True)
    artifacts_directory.mkdir(parents=True, exist_ok=True)

    metrics_path = reports_directory / "binary_classifier_metrics.json"
    confusion_path = reports_directory / "binary_confusion_matrix.csv"
    family_path = reports_directory / "attack_family_detection.csv"
    artifact_path = artifacts_directory / MODEL_FILENAME
    metadata_path = artifacts_directory / "model_metadata.json"

    train = load_complete_nsl_kdd(train_path)
    test = load_complete_nsl_kdd(test_path)
    mapped_labels = validate_label_mapping(train, test)
    X_train, y_train = split_features_and_target(train)
    X_test, y_test = split_features_and_target(test)

    model_pipeline = Pipeline(
        steps=[
            ("preprocessor", build_preprocessor()),
            ("classifier", RandomForestClassifier(**MODEL_PARAMETERS)),
        ]
    )

    training_started = perf_counter()
    model_pipeline.fit(X_train, y_train)
    training_duration = perf_counter() - training_started

    prediction_started = perf_counter()
    predictions = model_pipeline.predict(X_test)
    attack_probabilities = model_pipeline.predict_proba(X_test)[:, 1]
    prediction_duration = perf_counter() - prediction_started

    transformed_feature_count = len(
        model_pipeline.named_steps["preprocessor"].get_feature_names_out()
    )
    test_metrics, matrix = calculate_metrics(
        y_test, predictions, attack_probabilities
    )
    family_report = build_family_report(test, predictions)

    metrics_report = {
        "evaluation_policy": {
            "training_data": TRAIN_FILENAME,
            "evaluation_data": TEST_FILENAME,
            "test_set_used_for_fitting_or_tuning": False,
            "hyperparameter_tuning_performed": False,
            "classification_threshold": DEFAULT_THRESHOLD,
            "positive_class": "attack",
        },
        "train_row_count": int(len(train)),
        "test_row_count": int(len(test)),
        "feature_count_before_encoding": len(INCLUDED_FEATURE_COLUMNS),
        "transformed_feature_count_after_encoding": transformed_feature_count,
        "train_binary_distribution": {
            "normal": int((y_train == 0).sum()),
            "attack": int((y_train == 1).sum()),
        },
        "test_binary_distribution": {
            "normal": int((y_test == 0).sum()),
            "attack": int((y_test == 1).sum()),
        },
        "model_parameters": MODEL_PARAMETERS,
        "timing_seconds": {
            "training": training_duration,
            "prediction": prediction_duration,
        },
        "test_metrics": test_metrics,
    }
    write_json(metrics_path, metrics_report)

    pd.DataFrame(
        [
            {
                "actual": "normal",
                "predicted_normal": matrix[0][0],
                "predicted_attack": matrix[0][1],
            },
            {
                "actual": "attack",
                "predicted_normal": matrix[1][0],
                "predicted_attack": matrix[1][1],
            },
        ]
    ).to_csv(confusion_path, index=False)
    family_report.to_csv(family_path, index=False)

    joblib.dump(model_pipeline, artifact_path, compress=3)
    artifact_size = artifact_path.stat().st_size
    artifact_hash = sha256_file(artifact_path)

    metadata = {
        "project_model_name": "Athes Sentinel NSL-KDD Binary Random Forest",
        "task": "binary intrusion classification",
        "public_dataset": "NSL-KDD",
        "complete_source_filenames": [TRAIN_FILENAME, TEST_FILENAME],
        "training_row_count": int(len(train)),
        "test_row_count": int(len(test)),
        "target_mapping": {"normal": 0, "attack": 1},
        "included_feature_columns": INCLUDED_FEATURE_COLUMNS,
        "excluded_columns": {
            "label": "supervised target; excluded to prevent target leakage",
            "difficulty_level": "dataset difficulty metadata, not a traffic feature",
            "num_outbound_cmds": "constant zero-variance feature in both datasets",
        },
        "categorical_columns": CATEGORICAL_COLUMNS,
        "model_parameters": MODEL_PARAMETERS,
        "default_threshold": DEFAULT_THRESHOLD,
        "scikit_learn_version": sklearn.__version__,
        "python_version": platform.python_version(),
        "creation_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "evaluation_report_path": relative_path(metrics_path, root),
        "artifact_path": relative_path(artifact_path, root),
        "artifact_size_bytes": artifact_size,
        "artifact_sha256": artifact_hash,
        "all_normalized_labels_mapped": True,
        "mapped_normalized_labels": mapped_labels,
    }
    write_json(metadata_path, metadata)

    print_summary(
        train.shape,
        test.shape,
        transformed_feature_count,
        metrics_report,
        family_report,
        artifact_path,
        [metrics_path, confusion_path, family_path, metadata_path],
    )


if __name__ == "__main__":
    main()
