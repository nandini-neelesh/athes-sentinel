"""Select and calibrate an improved binary NSL-KDD model using validation only."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    fbeta_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from ml_pipeline.attack_mapping import get_attack_family
from ml_pipeline.nsl_kdd_schema import CATEGORICAL_COLUMNS, LABEL_COLUMN
from ml_pipeline.preprocessing import (
    EXCLUDED_COLUMNS,
    INCLUDED_FEATURE_COLUMNS,
    INCLUDED_NUMERIC_COLUMNS,
    build_preprocessor,
    load_complete_nsl_kdd,
    normalize_labels,
    split_features_and_target,
)

DATASET_DIRECTORY = Path("data") / "external" / "nsl-kdd"
TRAIN_FILENAME = "KDDTrain+.txt"
TEST_FILENAME = "KDDTest+.txt"
ARTIFACT_FILENAME = "nsl_kdd_improved_binary_pipeline.joblib"
VALIDATION_SIZE = 0.20
RANDOM_STATE = 42
FALSE_POSITIVE_RATE_LIMIT = 0.05
DEFAULT_THRESHOLD = 0.5
THRESHOLDS = np.arange(10, 91, dtype=int) / 100

HONESTY_STATEMENTS = [
    "Phase N2 already established a fixed baseline on the official test set.",
    (
        "Phase N2.1 model and threshold selection used only one new stratified "
        "train/validation split from KDDTrain+."
    ),
    "Final official-test evaluation is reported transparently.",
    (
        "No official-test metric was used to revise the selected candidate or "
        "threshold after evaluation."
    ),
    "The selected model is a limited baseline comparison, not a global optimum.",
    "NSL-KDD is a public benchmark and does not represent modern production traffic.",
    "Rare-attack detection is not claimed to be solved.",
]

CANDIDATES: list[dict[str, Any]] = [
    {
        "candidate": "candidate_a",
        "model_name": "Phase N2 baseline Random Forest",
        "classifier": "RandomForestClassifier",
        "parameters": {
            "n_estimators": 200,
            "max_depth": 25,
            "min_samples_leaf": 2,
            "class_weight": "balanced_subsample",
            "random_state": RANDOM_STATE,
            "n_jobs": -1,
        },
    },
    {
        "candidate": "candidate_b",
        "model_name": "Recall-oriented Random Forest",
        "classifier": "RandomForestClassifier",
        "parameters": {
            "n_estimators": 300,
            "max_depth": None,
            "min_samples_leaf": 1,
            "class_weight": {0: 1.0, 1: 2.0},
            "random_state": RANDOM_STATE,
            "n_jobs": -1,
        },
    },
    {
        "candidate": "candidate_c",
        "model_name": "Extra Trees",
        "classifier": "ExtraTreesClassifier",
        "parameters": {
            "n_estimators": 300,
            "max_depth": None,
            "min_samples_leaf": 1,
            "class_weight": "balanced",
            "random_state": RANDOM_STATE,
            "n_jobs": -1,
        },
    },
]


def repository_root() -> Path:
    """Resolve the repository root safely from this module's location."""
    return Path(__file__).resolve().parent.parent


def build_candidate_pipeline(candidate: dict[str, Any]) -> Pipeline:
    """Build a fresh preprocessing-plus-classifier pipeline for a candidate."""
    if candidate["classifier"] == "RandomForestClassifier":
        classifier = RandomForestClassifier(**candidate["parameters"])
    elif candidate["classifier"] == "ExtraTreesClassifier":
        classifier = ExtraTreesClassifier(**candidate["parameters"])
    else:
        raise ValueError(f"Unsupported classifier: {candidate['classifier']}")

    return Pipeline(
        steps=[
            ("preprocessor", build_preprocessor()),
            ("classifier", classifier),
        ]
    )


def validate_label_mapping(frame: pd.DataFrame, source_name: str) -> list[str]:
    """Fail clearly if a source contains a label absent from the family map."""
    labels = sorted(set(normalize_labels(frame[LABEL_COLUMN])))
    for label in labels:
        try:
            get_attack_family(label)
        except ValueError as error:
            raise ValueError(f"{source_name}: {error}") from error
    return labels


def attack_probabilities(pipeline: Pipeline, features: pd.DataFrame) -> np.ndarray:
    """Return probabilities for class 1 without assuming class-column order."""
    classifier = pipeline.named_steps["classifier"]
    class_positions = np.flatnonzero(classifier.classes_ == 1)
    if len(class_positions) != 1:
        raise ValueError("The fitted classifier does not contain binary attack class 1.")
    return pipeline.predict_proba(features)[:, int(class_positions[0])]


def safe_rate(numerator: int, denominator: int) -> float:
    """Calculate a rate safely when a class might be absent."""
    return float(numerator / denominator) if denominator else 0.0


def threshold_metrics(
    targets: pd.Series | np.ndarray,
    probabilities: np.ndarray,
    threshold: float,
) -> dict[str, Any]:
    """Calculate the metrics used for threshold and candidate selection."""
    predictions = (probabilities >= threshold).astype("int8")
    matrix = confusion_matrix(targets, predictions, labels=[0, 1])
    true_negatives, false_positives, false_negatives, true_positives = (
        int(value) for value in matrix.ravel()
    )
    return {
        "threshold": float(threshold),
        "precision": float(
            precision_score(targets, predictions, zero_division=0)
        ),
        "recall": float(recall_score(targets, predictions, zero_division=0)),
        "f1": float(f1_score(targets, predictions, zero_division=0)),
        "f2": float(
            fbeta_score(targets, predictions, beta=2, zero_division=0)
        ),
        "false_positive_rate": safe_rate(
            false_positives, false_positives + true_negatives
        ),
        "false_negative_rate": safe_rate(
            false_negatives, false_negatives + true_positives
        ),
        "specificity": safe_rate(
            true_negatives, true_negatives + false_positives
        ),
        "true_negatives": true_negatives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "true_positives": true_positives,
    }


def choose_threshold(
    threshold_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], bool]:
    """Apply the stated FPR constraint and deterministic threshold tie-breakers."""
    constrained_rows = [
        row
        for row in threshold_rows
        if row["false_positive_rate"] <= FALSE_POSITIVE_RATE_LIMIT
    ]
    eligible_rows = constrained_rows or threshold_rows
    selected = max(
        eligible_rows,
        key=lambda row: (
            row["f2"],
            row["recall"],
            -row["false_positive_rate"],
            -abs(row["threshold"] - DEFAULT_THRESHOLD),
        ),
    )
    return selected, bool(constrained_rows)


def choose_candidate(
    candidate_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply the validation-only candidate selection and tie-break policy."""
    return max(
        candidate_rows,
        key=lambda row: (
            row["validation_f2"],
            row["validation_recall"],
            -row["validation_false_positive_rate"],
            row["validation_precision"],
        ),
    )


def complete_binary_metrics(
    targets: pd.Series,
    probabilities: np.ndarray,
    threshold: float,
) -> tuple[dict[str, Any], np.ndarray]:
    """Calculate complete official-test metrics at one fixed threshold."""
    predictions = (probabilities >= threshold).astype("int8")
    selection_metrics = threshold_metrics(targets, probabilities, threshold)
    metrics = {
        "threshold": float(threshold),
        "accuracy": float(accuracy_score(targets, predictions)),
        "balanced_accuracy": float(
            balanced_accuracy_score(targets, predictions)
        ),
        "precision": selection_metrics["precision"],
        "recall": selection_metrics["recall"],
        "f1": selection_metrics["f1"],
        "f2": selection_metrics["f2"],
        "roc_auc": float(roc_auc_score(targets, probabilities)),
        "pr_auc_average_precision": float(
            average_precision_score(targets, probabilities)
        ),
        "confusion_matrix": {
            "true_negatives": selection_metrics["true_negatives"],
            "false_positives": selection_metrics["false_positives"],
            "false_negatives": selection_metrics["false_negatives"],
            "true_positives": selection_metrics["true_positives"],
        },
        "false_positive_rate": selection_metrics["false_positive_rate"],
        "false_negative_rate": selection_metrics["false_negative_rate"],
        "specificity": selection_metrics["specificity"],
    }
    return metrics, predictions


def build_family_report(
    test: pd.DataFrame, predictions: np.ndarray
) -> pd.DataFrame:
    """Summarize final fixed-threshold outcomes by real attack family."""
    normalized_labels = normalize_labels(test[LABEL_COLUMN])
    families = normalized_labels.map(get_attack_family)
    prediction_series = pd.Series(predictions, index=test.index)
    rows: list[dict[str, Any]] = []

    for family in ["dos", "probe", "r2l", "u2r"]:
        family_predictions = prediction_series[families == family]
        total = int(len(family_predictions))
        detected = int((family_predictions == 1).sum())
        missed = int((family_predictions == 0).sum())
        rows.append(
            {
                "family": family,
                "total_test_records": total,
                "predicted_as_attack": detected,
                "missed_as_normal": missed,
                "detection_recall": safe_rate(detected, total),
                "correctly_predicted_normal": pd.NA,
                "falsely_flagged_attack": pd.NA,
                "false_positive_rate": pd.NA,
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
            "predicted_as_attack": pd.NA,
            "missed_as_normal": pd.NA,
            "detection_recall": pd.NA,
            "correctly_predicted_normal": correctly_normal,
            "falsely_flagged_attack": falsely_flagged,
            "false_positive_rate": safe_rate(falsely_flagged, normal_total),
        }
    )

    report = pd.DataFrame(rows)
    count_columns = [
        "total_test_records",
        "predicted_as_attack",
        "missed_as_normal",
        "correctly_predicted_normal",
        "falsely_flagged_attack",
    ]
    for column in count_columns:
        report[column] = report[column].astype("Int64")
    return report


def baseline_comparison_row(baseline_report: dict[str, Any]) -> dict[str, Any]:
    """Convert the committed N2 metrics into the N2.1 comparison schema."""
    metrics = baseline_report["test_metrics"]
    matrix = metrics["confusion_matrix"]
    precision = float(metrics["precision"])
    recall = float(metrics["recall"])
    f2_denominator = (4 * precision) + recall
    f2 = (5 * precision * recall / f2_denominator) if f2_denominator else 0.0
    return {
        "model": "Phase N2 baseline Random Forest",
        "threshold": baseline_report["evaluation_policy"][
            "classification_threshold"
        ],
        "precision": precision,
        "recall": recall,
        "f1": float(metrics["f1_score"]),
        "f2": f2,
        "false_positive_rate": float(metrics["false_positive_rate"]),
        "false_negative_rate": float(metrics["false_negative_rate"]),
        "true_positives": int(matrix["true_positives"]),
        "false_positives": int(matrix["false_positives"]),
        "false_negatives": int(matrix["false_negatives"]),
        "true_negatives": int(matrix["true_negatives"]),
    }


def improved_comparison_row(
    model_name: str, metrics: dict[str, Any]
) -> dict[str, Any]:
    """Convert selected-threshold test metrics into the comparison schema."""
    matrix = metrics["confusion_matrix"]
    return {
        "model": f"Phase N2.1 selected {model_name}",
        "threshold": metrics["threshold"],
        "precision": metrics["precision"],
        "recall": metrics["recall"],
        "f1": metrics["f1"],
        "f2": metrics["f2"],
        "false_positive_rate": metrics["false_positive_rate"],
        "false_negative_rate": metrics["false_negative_rate"],
        "true_positives": matrix["true_positives"],
        "false_positives": matrix["false_positives"],
        "false_negatives": matrix["false_negatives"],
        "true_negatives": matrix["true_negatives"],
    }


def sha256_file(path: Path) -> str:
    """Hash a potentially large artifact without loading it all into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for block in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, content: dict[str, Any]) -> None:
    """Write a human-readable UTF-8 JSON document."""
    path.write_text(json.dumps(content, indent=2), encoding="utf-8")


def relative_path(path: Path, root: Path) -> str:
    """Return a portable repository-relative path."""
    return path.relative_to(root).as_posix()


def print_summary(
    train_shape: tuple[int, int],
    test_shape: tuple[int, int],
    candidate_rows: list[dict[str, Any]],
    selected: dict[str, Any],
    transformed_feature_count: int,
    test_metrics: dict[str, Any],
    default_metrics: dict[str, Any],
    family_report: pd.DataFrame,
    durations: dict[str, Any],
    artifact_path: Path,
    report_paths: list[Path],
) -> None:
    """Print concise selection, evaluation, and artifact outcomes."""
    print(f"Complete train shape: {train_shape}")
    print(f"Complete test shape: {test_shape}")
    print(f"Selected features before encoding: {len(INCLUDED_FEATURE_COLUMNS)}")
    print(f"Transformed features after encoding: {transformed_feature_count}")
    print("Candidate validation results:")
    for row in candidate_rows:
        print(
            f"  {row['candidate']} ({row['model_name']}): "
            f"threshold={row['selected_threshold']:.2f}, "
            f"precision={row['validation_precision']:.6f}, "
            f"recall={row['validation_recall']:.6f}, "
            f"F2={row['validation_f2']:.6f}, "
            f"FPR={row['validation_false_positive_rate']:.6f}"
        )
    print(
        f"Selected: {selected['candidate']} ({selected['model_name']}) "
        f"at validation threshold {selected['selected_threshold']:.2f}"
    )
    print(
        "Final fit/prediction time (seconds): "
        f"{durations['final_full_training']:.3f}/"
        f"{durations['official_test_prediction']:.3f}"
    )
    print(
        "Official test at selected threshold: "
        f"precision={test_metrics['precision']:.6f}, "
        f"recall={test_metrics['recall']:.6f}, "
        f"F1={test_metrics['f1']:.6f}, "
        f"F2={test_metrics['f2']:.6f}, "
        f"ROC-AUC={test_metrics['roc_auc']:.6f}, "
        f"PR-AUC={test_metrics['pr_auc_average_precision']:.6f}, "
        f"FPR={test_metrics['false_positive_rate']:.6f}"
    )
    print(
        "Official test at threshold 0.50: "
        f"precision={default_metrics['precision']:.6f}, "
        f"recall={default_metrics['recall']:.6f}, "
        f"F1={default_metrics['f1']:.6f}, "
        f"F2={default_metrics['f2']:.6f}, "
        f"FPR={default_metrics['false_positive_rate']:.6f}"
    )
    matrix = test_metrics["confusion_matrix"]
    print(
        "Selected-threshold confusion matrix (TN, FP, FN, TP): "
        f"{matrix['true_negatives']}, {matrix['false_positives']}, "
        f"{matrix['false_negatives']}, {matrix['true_positives']}"
    )
    print("Family-level outcomes:")
    for row in family_report.itertuples(index=False):
        if row.family == "normal":
            print(f"  normal false-positive rate: {row.false_positive_rate:.6f}")
        else:
            print(f"  {row.family} detection recall: {row.detection_recall:.6f}")
    print(f"Artifact: {artifact_path} ({artifact_path.stat().st_size} bytes)")
    print("Generated reports:")
    for path in report_paths:
        print(f"  {path}")


def main() -> None:
    """Run validation-only selection, full refit, and fixed official evaluation."""
    root = repository_root()
    train_path = root / DATASET_DIRECTORY / TRAIN_FILENAME
    test_path = root / DATASET_DIRECTORY / TEST_FILENAME
    reports_directory = root / "ml_pipeline" / "reports"
    artifacts_directory = root / "ml_pipeline" / "artifacts"
    reports_directory.mkdir(parents=True, exist_ok=True)
    artifacts_directory.mkdir(parents=True, exist_ok=True)

    candidate_path = reports_directory / "binary_candidate_validation.csv"
    threshold_path = reports_directory / "binary_threshold_search.csv"
    metrics_path = reports_directory / "improved_binary_metrics.json"
    confusion_path = (
        reports_directory / "improved_binary_confusion_matrix.csv"
    )
    family_path = reports_directory / "improved_attack_family_detection.csv"
    comparison_path = reports_directory / "baseline_vs_improved.csv"
    artifact_path = artifacts_directory / ARTIFACT_FILENAME
    metadata_path = artifacts_directory / "improved_model_metadata.json"
    baseline_metrics_path = reports_directory / "binary_classifier_metrics.json"

    # Only the complete training file is loaded during model and threshold selection.
    train = load_complete_nsl_kdd(train_path)
    train_labels = validate_label_mapping(train, TRAIN_FILENAME)
    all_train_features, all_train_targets = split_features_and_target(train)
    (
        candidate_train_features,
        validation_features,
        candidate_train_targets,
        validation_targets,
    ) = train_test_split(
        all_train_features,
        all_train_targets,
        test_size=VALIDATION_SIZE,
        random_state=RANDOM_STATE,
        stratify=all_train_targets,
    )

    candidate_rows: list[dict[str, Any]] = []
    all_threshold_rows: list[dict[str, Any]] = []
    for candidate in CANDIDATES:
        pipeline = build_candidate_pipeline(candidate)
        training_started = perf_counter()
        pipeline.fit(candidate_train_features, candidate_train_targets)
        candidate_training_duration = perf_counter() - training_started

        prediction_started = perf_counter()
        validation_probabilities = attack_probabilities(
            pipeline, validation_features
        )
        validation_prediction_duration = perf_counter() - prediction_started

        candidate_threshold_rows: list[dict[str, Any]] = []
        for threshold in THRESHOLDS:
            row = threshold_metrics(
                validation_targets, validation_probabilities, float(threshold)
            )
            row.update(
                {
                    "candidate": candidate["candidate"],
                    "model_name": candidate["model_name"],
                    "meets_fpr_constraint": (
                        row["false_positive_rate"]
                        <= FALSE_POSITIVE_RATE_LIMIT
                    ),
                }
            )
            candidate_threshold_rows.append(row)

        selected_threshold_row, constraint_available = choose_threshold(
            candidate_threshold_rows
        )
        for row in candidate_threshold_rows:
            row["selected_for_candidate"] = (
                row["threshold"] == selected_threshold_row["threshold"]
            )
        all_threshold_rows.extend(candidate_threshold_rows)

        candidate_rows.append(
            {
                "candidate": candidate["candidate"],
                "model_name": candidate["model_name"],
                "classifier": candidate["classifier"],
                "parameters": json.dumps(
                    candidate["parameters"], sort_keys=True
                ),
                "selected_threshold": selected_threshold_row["threshold"],
                "fpr_constraint_satisfied": constraint_available,
                "validation_precision": selected_threshold_row["precision"],
                "validation_recall": selected_threshold_row["recall"],
                "validation_f1": selected_threshold_row["f1"],
                "validation_f2": selected_threshold_row["f2"],
                "validation_false_positive_rate": selected_threshold_row[
                    "false_positive_rate"
                ],
                "validation_false_negative_rate": selected_threshold_row[
                    "false_negative_rate"
                ],
                "validation_specificity": selected_threshold_row[
                    "specificity"
                ],
                "validation_true_negatives": selected_threshold_row[
                    "true_negatives"
                ],
                "validation_false_positives": selected_threshold_row[
                    "false_positives"
                ],
                "validation_false_negatives": selected_threshold_row[
                    "false_negatives"
                ],
                "validation_true_positives": selected_threshold_row[
                    "true_positives"
                ],
                "validation_roc_auc": float(
                    roc_auc_score(
                        validation_targets, validation_probabilities
                    )
                ),
                "validation_pr_auc": float(
                    average_precision_score(
                        validation_targets, validation_probabilities
                    )
                ),
                "candidate_training_seconds": candidate_training_duration,
                "validation_prediction_seconds": (
                    validation_prediction_duration
                ),
                "selected_candidate": False,
            }
        )

    selected_row = choose_candidate(candidate_rows)
    selected_row["selected_candidate"] = True
    selected_candidate = next(
        candidate
        for candidate in CANDIDATES
        if candidate["candidate"] == selected_row["candidate"]
    )
    selected_threshold = float(selected_row["selected_threshold"])

    # Lock the validation-selected configuration before touching the test file.
    final_pipeline = build_candidate_pipeline(selected_candidate)
    final_training_started = perf_counter()
    final_pipeline.fit(all_train_features, all_train_targets)
    final_training_duration = perf_counter() - final_training_started

    # The official test file is loaded only after candidate and threshold are fixed.
    test = load_complete_nsl_kdd(test_path)
    test_labels = validate_label_mapping(test, TEST_FILENAME)
    test_features, test_targets = split_features_and_target(test)
    test_prediction_started = perf_counter()
    test_probabilities = attack_probabilities(final_pipeline, test_features)
    test_prediction_duration = perf_counter() - test_prediction_started

    selected_test_metrics, selected_predictions = complete_binary_metrics(
        test_targets, test_probabilities, selected_threshold
    )
    default_test_metrics, _ = complete_binary_metrics(
        test_targets, test_probabilities, DEFAULT_THRESHOLD
    )
    family_report = build_family_report(test, selected_predictions)
    transformed_feature_count = len(
        final_pipeline.named_steps["preprocessor"].get_feature_names_out()
    )

    candidate_frame = pd.DataFrame(candidate_rows)
    candidate_frame.to_csv(candidate_path, index=False)
    pd.DataFrame(all_threshold_rows).to_csv(threshold_path, index=False)

    matrix = selected_test_metrics["confusion_matrix"]
    pd.DataFrame(
        [
            {
                "actual": "normal",
                "predicted_normal": matrix["true_negatives"],
                "predicted_attack": matrix["false_positives"],
            },
            {
                "actual": "attack",
                "predicted_normal": matrix["false_negatives"],
                "predicted_attack": matrix["true_positives"],
            },
        ]
    ).to_csv(confusion_path, index=False)
    family_report.to_csv(family_path, index=False)

    if not baseline_metrics_path.is_file():
        raise FileNotFoundError(
            f"Required Phase N2 baseline report not found: {baseline_metrics_path}"
        )
    baseline_report = json.loads(
        baseline_metrics_path.read_text(encoding="utf-8")
    )
    baseline_row = baseline_comparison_row(baseline_report)
    improved_row = improved_comparison_row(
        selected_candidate["model_name"], selected_test_metrics
    )
    comparison_frame = pd.DataFrame([baseline_row, improved_row])
    comparison_frame.to_csv(comparison_path, index=False)

    durations = {
        "candidate_training_total": float(
            candidate_frame["candidate_training_seconds"].sum()
        ),
        "candidate_validation_prediction_total": float(
            candidate_frame["validation_prediction_seconds"].sum()
        ),
        "final_full_training": final_training_duration,
        "official_test_prediction": test_prediction_duration,
    }
    validation_metrics = {
        "threshold": selected_row["selected_threshold"],
        "precision": selected_row["validation_precision"],
        "recall": selected_row["validation_recall"],
        "f1": selected_row["validation_f1"],
        "f2": selected_row["validation_f2"],
        "false_positive_rate": selected_row[
            "validation_false_positive_rate"
        ],
        "false_negative_rate": selected_row[
            "validation_false_negative_rate"
        ],
        "specificity": selected_row["validation_specificity"],
        "confusion_matrix": {
            "true_negatives": selected_row["validation_true_negatives"],
            "false_positives": selected_row["validation_false_positives"],
            "false_negatives": selected_row["validation_false_negatives"],
            "true_positives": selected_row["validation_true_positives"],
        },
        "roc_auc": selected_row["validation_roc_auc"],
        "pr_auc_average_precision": selected_row["validation_pr_auc"],
    }
    selection_policy = {
        "threshold_grid": {
            "minimum": 0.10,
            "maximum": 0.90,
            "increment": 0.01,
        },
        "threshold_selection": (
            "Prefer FPR <= 0.05; maximize validation F2, then recall, then "
            "lower FPR, then threshold closest to 0.5."
        ),
        "candidate_selection": (
            "Maximize selected-threshold validation F2, then recall, then "
            "lower FPR, then precision."
        ),
        "official_test_metrics_used_for_selection": False,
    }
    metrics_report = {
        "honesty_statements": HONESTY_STATEMENTS,
        "data_policy": {
            "complete_training_filename": TRAIN_FILENAME,
            "complete_test_filename": TEST_FILENAME,
            "complete_training_rows": int(len(train)),
            "complete_test_rows": int(len(test)),
            "candidate_training_rows": int(len(candidate_train_targets)),
            "validation_rows": int(len(validation_targets)),
            "validation_fraction": VALIDATION_SIZE,
            "stratified_binary_target": True,
            "random_state": RANDOM_STATE,
            "sampling_or_synthetic_data_used": False,
        },
        "feature_policy": {
            "features_before_encoding": len(INCLUDED_FEATURE_COLUMNS),
            "categorical_features": len(CATEGORICAL_COLUMNS),
            "numeric_features": len(INCLUDED_NUMERIC_COLUMNS),
            "transformed_features_after_encoding": transformed_feature_count,
            "excluded_columns": EXCLUDED_COLUMNS,
        },
        "candidate_selection_policy": selection_policy,
        "selected_candidate": {
            "candidate": selected_candidate["candidate"],
            "model_name": selected_candidate["model_name"],
            "classifier": selected_candidate["classifier"],
            "parameters": selected_candidate["parameters"],
            "selected_validation_threshold": selected_threshold,
            "selection_reason": (
                "Selected by the declared validation F2 and tie-break policy."
            ),
        },
        "selected_candidate_validation_metrics": validation_metrics,
        "official_test_metrics_selected_threshold": selected_test_metrics,
        "official_test_metrics_threshold_0_5_comparison_only": (
            default_test_metrics
        ),
        "durations_seconds": durations,
        "report_paths": {
            "candidate_validation": relative_path(candidate_path, root),
            "threshold_search": relative_path(threshold_path, root),
            "confusion_matrix": relative_path(confusion_path, root),
            "family_detection": relative_path(family_path, root),
            "baseline_comparison": relative_path(comparison_path, root),
        },
    }
    write_json(metrics_path, metrics_report)

    joblib.dump(final_pipeline, artifact_path, compress=3)
    artifact_size = artifact_path.stat().st_size
    artifact_hash = sha256_file(artifact_path)
    metadata = {
        "project_model_name": "Athes Sentinel improved NSL-KDD binary detector",
        "selected_model_name": selected_candidate["model_name"],
        "selected_model_parameters": selected_candidate["parameters"],
        "validation_split_policy": {
            "source": TRAIN_FILENAME,
            "candidate_training_fraction": 0.80,
            "validation_fraction": VALIDATION_SIZE,
            "random_state": RANDOM_STATE,
            "stratify": "binary target",
        },
        "candidate_selection_policy": selection_policy,
        "selected_threshold": selected_threshold,
        "selected_candidate_validation_metrics": validation_metrics,
        "complete_training_row_count": int(len(train)),
        "complete_test_row_count": int(len(test)),
        "feature_policy": metrics_report["feature_policy"],
        "official_test_metrics_selected_threshold": selected_test_metrics,
        "official_test_metrics_threshold_0_5_comparison_only": (
            default_test_metrics
        ),
        "scikit_learn_version": sklearn.__version__,
        "creation_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "artifact_path": relative_path(artifact_path, root),
        "artifact_size_bytes": artifact_size,
        "artifact_sha256": artifact_hash,
        "evaluation_report_path": relative_path(metrics_path, root),
        "all_training_labels_mapped": True,
        "all_test_labels_mapped": True,
        "mapped_training_labels": train_labels,
        "mapped_test_labels": test_labels,
        "selection_without_official_test_data": True,
        "selection_statement": (
            "The model and threshold were selected using only KDDTrain+ "
            "candidate-training and validation partitions. Official-test "
            "metrics were not used to revise either choice."
        ),
        "honesty_statements": HONESTY_STATEMENTS,
    }
    write_json(metadata_path, metadata)

    print_summary(
        train.shape,
        test.shape,
        candidate_rows,
        selected_row,
        transformed_feature_count,
        selected_test_metrics,
        default_test_metrics,
        family_report,
        durations,
        artifact_path,
        [
            candidate_path,
            threshold_path,
            metrics_path,
            confusion_path,
            family_path,
            comparison_path,
            metadata_path,
        ],
    )


if __name__ == "__main__":
    main()
