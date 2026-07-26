"""Run a controlled Random Forest plus Isolation Forest hybrid experiment."""

from __future__ import annotations

import hashlib
import inspect
import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import IsolationForest, RandomForestClassifier
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
from sklearn.preprocessing import OneHotEncoder, StandardScaler

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
ARTIFACT_FILENAME = "nsl_kdd_hybrid_detector.joblib"
RANDOM_STATE = 42
RF_ONLY_THRESHOLD = 0.38
FPR_LIMIT = 0.05
RF_WEIGHTS = [0.50, 0.60, 0.70, 0.80, 0.90]
THRESHOLDS = np.arange(10, 91, dtype=int) / 100
ATTACK_FAMILIES = ["dos", "probe", "r2l", "u2r"]

RF_PARAMETERS = {
    "n_estimators": 300,
    "max_depth": None,
    "min_samples_leaf": 1,
    "class_weight": {0: 1.0, 1: 2.0},
    "random_state": RANDOM_STATE,
    "n_jobs": -1,
}
IF_PARAMETERS = {
    "n_estimators": 300,
    "contamination": "auto",
    "max_samples": "auto",
    "random_state": RANDOM_STATE,
    "n_jobs": -1,
}


def repository_root() -> Path:
    """Resolve the repository root safely from this script's location."""
    return Path(__file__).resolve().parent.parent


def validate_label_mapping(frame: pd.DataFrame, source_name: str) -> list[str]:
    """Verify that every normalized label has an explicit family mapping."""
    labels = sorted(set(normalize_labels(frame[LABEL_COLUMN])))
    for label in labels:
        try:
            get_attack_family(label)
        except ValueError as error:
            raise ValueError(f"{source_name}: {error}") from error
    return labels


def build_rf_pipeline() -> Pipeline:
    """Build a fresh copy of the selected N2.1 Random Forest pipeline."""
    return Pipeline(
        steps=[
            ("preprocessor", build_preprocessor()),
            ("classifier", RandomForestClassifier(**RF_PARAMETERS)),
        ]
    )


def build_if_preprocessor() -> ColumnTransformer:
    """Build Isolation Forest preprocessing with scaled numeric features."""
    encoder_parameters: dict[str, object] = {"handle_unknown": "ignore"}
    if "sparse_output" in inspect.signature(OneHotEncoder).parameters:
        encoder_parameters["sparse_output"] = True
    else:
        encoder_parameters["sparse"] = True

    return ColumnTransformer(
        transformers=[
            (
                "categorical",
                OneHotEncoder(**encoder_parameters),
                CATEGORICAL_COLUMNS,
            ),
            (
                "numeric",
                StandardScaler(with_mean=False),
                INCLUDED_NUMERIC_COLUMNS,
            ),
        ],
        # Preserve a sparse combined matrix for the anomaly detector.
        sparse_threshold=1.0,
    )


def build_if_pipeline() -> Pipeline:
    """Build a fresh Isolation Forest pipeline for normal-only fitting."""
    return Pipeline(
        steps=[
            ("preprocessor", build_if_preprocessor()),
            ("isolation_forest", IsolationForest(**IF_PARAMETERS)),
        ]
    )


def rf_attack_probabilities(
    pipeline: Pipeline, features: pd.DataFrame
) -> np.ndarray:
    """Return the fitted Random Forest probability for attack class 1."""
    classifier = pipeline.named_steps["classifier"]
    class_positions = np.flatnonzero(classifier.classes_ == 1)
    if len(class_positions) != 1:
        raise ValueError("The fitted Random Forest has no unique attack class 1.")
    return pipeline.predict_proba(features)[:, int(class_positions[0])]


def raw_anomaly_scores(
    pipeline: Pipeline, features: pd.DataFrame
) -> np.ndarray:
    """Return Isolation Forest scores where larger means more anomalous."""
    return -pipeline.decision_function(features)


def calculate_calibration_bounds(
    fitted_if_pipeline: Pipeline, normal_fit_features: pd.DataFrame
) -> tuple[float, float]:
    """Calculate 1st/99th percentile bounds from fitting normals only."""
    scores = raw_anomaly_scores(fitted_if_pipeline, normal_fit_features)
    lower = float(np.percentile(scores, 1))
    upper = float(np.percentile(scores, 99))
    if lower == upper:
        raise ValueError(
            "Isolation Forest anomaly calibration bounds are equal; "
            "cannot scale anomaly scores."
        )
    return lower, upper


def calibrate_anomaly_scores(
    raw_scores: np.ndarray, lower: float, upper: float
) -> np.ndarray:
    """Scale future raw anomaly scores to the fixed [0, 1] interval."""
    if lower == upper:
        raise ValueError(
            "Isolation Forest anomaly calibration bounds are equal; "
            "cannot scale anomaly scores."
        )
    return np.clip((raw_scores - lower) / (upper - lower), 0.0, 1.0)


def safe_rate(numerator: int, denominator: int) -> float:
    """Calculate a rate safely when a class might be absent."""
    return float(numerator / denominator) if denominator else 0.0


def attack_family_recalls(
    targets: pd.Series,
    predictions: np.ndarray,
    families: pd.Series,
) -> dict[str, float]:
    """Calculate binary detection recall for each mapped attack family."""
    prediction_series = pd.Series(predictions, index=targets.index)
    recalls: dict[str, float] = {}
    for family in ATTACK_FAMILIES:
        family_predictions = prediction_series[families == family]
        detected = int((family_predictions == 1).sum())
        recalls[family] = safe_rate(detected, int(len(family_predictions)))
    return recalls


def calculate_metrics(
    targets: pd.Series,
    scores: np.ndarray,
    threshold: float,
    families: pd.Series,
    include_ranking_metrics: bool = False,
) -> tuple[dict[str, Any], np.ndarray]:
    """Calculate binary and family metrics at a fixed score threshold."""
    predictions = (scores >= threshold).astype("int8")
    matrix = confusion_matrix(targets, predictions, labels=[0, 1])
    true_negatives, false_positives, false_negatives, true_positives = (
        int(value) for value in matrix.ravel()
    )
    family_recalls = attack_family_recalls(targets, predictions, families)
    metrics: dict[str, Any] = {
        "threshold": float(threshold),
        "accuracy": float(accuracy_score(targets, predictions)),
        "balanced_accuracy": float(
            balanced_accuracy_score(targets, predictions)
        ),
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
        "dos_recall": family_recalls["dos"],
        "probe_recall": family_recalls["probe"],
        "r2l_recall": family_recalls["r2l"],
        "u2r_recall": family_recalls["u2r"],
        "macro_attack_family_recall": float(
            np.mean(list(family_recalls.values()))
        ),
    }
    if include_ranking_metrics:
        metrics["roc_auc"] = float(roc_auc_score(targets, scores))
        metrics["pr_auc_average_precision"] = float(
            average_precision_score(targets, scores)
        )
    return metrics, predictions


def choose_fusion(
    search_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], bool]:
    """Apply the fixed validation selection and complete tie-break policy."""
    constrained = [
        row
        for row in search_rows
        if row["false_positive_rate"] <= FPR_LIMIT
    ]
    eligible = constrained or search_rows
    selected = max(
        eligible,
        key=lambda row: (
            row["f2"],
            row["recall"],
            row["macro_attack_family_recall"],
            -row["false_positive_rate"],
            row["precision"],
            -abs(row["rf_weight"] - 0.70),
            -abs(row["threshold"] - 0.50),
        ),
    )
    return selected, bool(constrained)


def internal_comparison_row(
    detector: str,
    rf_weight: float,
    if_weight: float,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    """Format holdout metrics for a transparent two-row comparison."""
    return {
        "detector": detector,
        "rf_weight": rf_weight,
        "if_weight": if_weight,
        **metrics,
    }


def build_family_report(
    test: pd.DataFrame, predictions: np.ndarray
) -> pd.DataFrame:
    """Create official-test family results for attacks and normal traffic."""
    families = normalize_labels(test[LABEL_COLUMN]).map(get_attack_family)
    prediction_series = pd.Series(predictions, index=test.index)
    rows: list[dict[str, Any]] = []
    for family in ATTACK_FAMILIES:
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
    for column in [
        "total_test_records",
        "predicted_as_attack",
        "missed_as_normal",
        "correctly_predicted_normal",
        "falsely_flagged_attack",
    ]:
        report[column] = report[column].astype("Int64")
    return report


def build_test_only_label_report(
    train: pd.DataFrame,
    test: pd.DataFrame,
    predictions: np.ndarray,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Report aggregate and per-label detection for test-only attack labels."""
    train_labels = set(normalize_labels(train[LABEL_COLUMN]))
    normalized_test_labels = normalize_labels(test[LABEL_COLUMN])
    test_labels = set(normalized_test_labels)
    test_only_attack_labels = sorted(
        label
        for label in test_labels - train_labels
        if get_attack_family(label) != "normal"
    )
    prediction_series = pd.Series(predictions, index=test.index)
    detail_rows: list[dict[str, Any]] = []
    for label in test_only_attack_labels:
        label_predictions = prediction_series[normalized_test_labels == label]
        total = int(len(label_predictions))
        detected = int((label_predictions == 1).sum())
        detail_rows.append(
            {
                "scope": "label",
                "label": label,
                "total_test_records": total,
                "detected_records": detected,
                "missed_records": total - detected,
                "recall": safe_rate(detected, total),
            }
        )

    total_records = sum(row["total_test_records"] for row in detail_rows)
    total_detected = sum(row["detected_records"] for row in detail_rows)
    aggregate = {
        "test_only_attack_labels": test_only_attack_labels,
        "total_test_only_attack_records": total_records,
        "detected_records": total_detected,
        "missed_records": total_records - total_detected,
        "aggregate_recall": safe_rate(total_detected, total_records),
    }
    aggregate_row = {
        "scope": "aggregate",
        "label": "ALL_TEST_ONLY_ATTACK_LABELS",
        "total_test_records": total_records,
        "detected_records": total_detected,
        "missed_records": total_records - total_detected,
        "recall": aggregate["aggregate_recall"],
    }
    return pd.DataFrame([aggregate_row, *detail_rows]), aggregate


def historical_comparison_row(
    phase: str,
    model_name: str,
    threshold: float,
    metrics: dict[str, Any],
    family_report: pd.DataFrame,
    phase_n2: bool = False,
) -> dict[str, Any]:
    """Normalize committed N2/N2.1 metrics for the three-way comparison."""
    if phase_n2:
        precision = float(metrics["precision"])
        recall = float(metrics["recall"])
        denominator = (4 * precision) + recall
        f2 = (5 * precision * recall / denominator) if denominator else 0.0
        f1 = float(metrics["f1_score"])
        specificity = float(metrics["specificity_true_negative_rate"])
    else:
        precision = float(metrics["precision"])
        recall = float(metrics["recall"])
        f2 = float(metrics["f2"])
        f1 = float(metrics["f1"])
        specificity = float(metrics["specificity"])

    matrix = metrics["confusion_matrix"]
    families = family_report.set_index("family")
    return {
        "phase": phase,
        "model": model_name,
        "threshold": threshold,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "f2": f2,
        "false_positive_rate": float(metrics["false_positive_rate"]),
        "false_negative_rate": float(metrics["false_negative_rate"]),
        "specificity": specificity,
        "true_negatives": int(matrix["true_negatives"]),
        "false_positives": int(matrix["false_positives"]),
        "false_negatives": int(matrix["false_negatives"]),
        "true_positives": int(matrix["true_positives"]),
        "dos_recall": float(families.loc["dos", "detection_recall"]),
        "probe_recall": float(families.loc["probe", "detection_recall"]),
        "r2l_recall": float(families.loc["r2l", "detection_recall"]),
        "u2r_recall": float(families.loc["u2r", "detection_recall"]),
    }


def hybrid_comparison_row(
    threshold: float,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    """Format accepted N2.2 official metrics for comparison."""
    return {
        "phase": "N2.2",
        "model": "accepted RF plus Isolation Forest hybrid",
        "threshold": threshold,
        "precision": metrics["precision"],
        "recall": metrics["recall"],
        "f1": metrics["f1"],
        "f2": metrics["f2"],
        "false_positive_rate": metrics["false_positive_rate"],
        "false_negative_rate": metrics["false_negative_rate"],
        "specificity": metrics["specificity"],
        "true_negatives": metrics["true_negatives"],
        "false_positives": metrics["false_positives"],
        "false_negatives": metrics["false_negatives"],
        "true_positives": metrics["true_positives"],
        "dos_recall": metrics["dos_recall"],
        "probe_recall": metrics["probe_recall"],
        "r2l_recall": metrics["r2l_recall"],
        "u2r_recall": metrics["u2r_recall"],
    }


def sha256_file(path: Path) -> str:
    """Hash a model artifact without loading it entirely into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for block in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, content: dict[str, Any]) -> None:
    """Write a human-readable UTF-8 JSON report."""
    path.write_text(json.dumps(content, indent=2), encoding="utf-8")


def relative_path(path: Path, root: Path) -> str:
    """Return a portable repository-relative path for metadata."""
    return path.relative_to(root).as_posix()


def remove_stale_accepted_outputs(paths: list[Path]) -> None:
    """Ensure a rejected rerun cannot leave accepted-only outputs behind."""
    for path in paths:
        if path.is_file():
            path.unlink()


def print_summary(
    partition_sizes: dict[str, int],
    normal_fit_count: int,
    rf_feature_count: int,
    if_feature_count: int,
    calibration_bounds: dict[str, float],
    selected: dict[str, Any],
    rf_holdout: dict[str, Any],
    hybrid_holdout: dict[str, Any],
    outcome: str,
    durations: dict[str, float],
    always_report_paths: list[Path],
    official_metrics: dict[str, Any] | None = None,
    test_only_summary: dict[str, Any] | None = None,
    artifact_path: Path | None = None,
    artifact_hash: str | None = None,
    accepted_report_paths: list[Path] | None = None,
) -> None:
    """Print concise controlled-experiment outcomes."""
    print(
        "Training-only partitions (fit/fusion/holdout): "
        f"{partition_sizes['detector_fitting']}/"
        f"{partition_sizes['fusion_selection']}/"
        f"{partition_sizes['acceptance_holdout']}"
    )
    print(f"Normal records used for initial Isolation Forest fit: {normal_fit_count}")
    print(f"Transformed features (RF/IF): {rf_feature_count}/{if_feature_count}")
    print(
        "Initial anomaly calibration bounds (1st/99th percentiles): "
        f"{calibration_bounds['lower']:.12f}/"
        f"{calibration_bounds['upper']:.12f}"
    )
    print(
        "Selected fusion (RF weight/IF weight/threshold): "
        f"{selected['rf_weight']:.2f}/"
        f"{selected['if_weight']:.2f}/"
        f"{selected['threshold']:.2f}"
    )
    print(
        "Fusion-selection metrics (F2/recall/FPR): "
        f"{selected['f2']:.6f}/"
        f"{selected['recall']:.6f}/"
        f"{selected['false_positive_rate']:.6f}"
    )
    print(
        "Holdout RF-only metrics (F2/recall/FPR): "
        f"{rf_holdout['f2']:.6f}/"
        f"{rf_holdout['recall']:.6f}/"
        f"{rf_holdout['false_positive_rate']:.6f}"
    )
    print(
        "Holdout hybrid metrics (F2/recall/FPR): "
        f"{hybrid_holdout['f2']:.6f}/"
        f"{hybrid_holdout['recall']:.6f}/"
        f"{hybrid_holdout['false_positive_rate']:.6f}"
    )
    print(f"Acceptance decision: {outcome}")
    print("Durations (seconds):")
    for name, duration in durations.items():
        print(f"  {name}: {duration:.3f}")
    if official_metrics is not None:
        print(
            "Official hybrid test metrics "
            "(precision/recall/F1/F2/FPR/ROC-AUC/PR-AUC): "
            f"{official_metrics['precision']:.6f}/"
            f"{official_metrics['recall']:.6f}/"
            f"{official_metrics['f1']:.6f}/"
            f"{official_metrics['f2']:.6f}/"
            f"{official_metrics['false_positive_rate']:.6f}/"
            f"{official_metrics['roc_auc']:.6f}/"
            f"{official_metrics['pr_auc_average_precision']:.6f}"
        )
    if test_only_summary is not None:
        print(
            "Test-only attack-label recall: "
            f"{test_only_summary['aggregate_recall']:.6f}"
        )
    print("Generated reports:")
    for path in [*always_report_paths, *(accepted_report_paths or [])]:
        print(f"  {path}")
    if artifact_path is not None and artifact_hash is not None:
        print(
            f"Artifact: {artifact_path} "
            f"({artifact_path.stat().st_size} bytes, SHA-256 {artifact_hash})"
        )


def main() -> None:
    """Run the gated training-only hybrid experiment."""
    root = repository_root()
    train_path = root / DATASET_DIRECTORY / TRAIN_FILENAME
    test_path = root / DATASET_DIRECTORY / TEST_FILENAME
    reports_directory = root / "ml_pipeline" / "reports"
    artifacts_directory = root / "ml_pipeline" / "artifacts"
    reports_directory.mkdir(parents=True, exist_ok=True)
    artifacts_directory.mkdir(parents=True, exist_ok=True)

    fusion_search_path = reports_directory / "hybrid_fusion_search.csv"
    selection_path = reports_directory / "hybrid_selection_metrics.json"
    holdout_path = (
        reports_directory / "hybrid_internal_holdout_comparison.csv"
    )
    summary_path = reports_directory / "hybrid_experiment_summary.json"
    metadata_path = artifacts_directory / "hybrid_model_metadata.json"
    artifact_path = artifacts_directory / ARTIFACT_FILENAME
    official_metrics_path = (
        reports_directory / "hybrid_official_test_metrics.json"
    )
    official_confusion_path = (
        reports_directory / "hybrid_official_confusion_matrix.csv"
    )
    official_family_path = (
        reports_directory / "hybrid_attack_family_detection.csv"
    )
    test_only_path = (
        reports_directory / "hybrid_test_only_label_detection.csv"
    )
    three_way_path = reports_directory / "n2_n21_n22_comparison.csv"
    accepted_only_paths = [
        artifact_path,
        official_metrics_path,
        official_confusion_path,
        official_family_path,
        test_only_path,
        three_way_path,
    ]
    remove_stale_accepted_outputs(accepted_only_paths)

    train = load_complete_nsl_kdd(train_path)
    mapped_train_labels = validate_label_mapping(train, TRAIN_FILENAME)
    all_features, all_targets = split_features_and_target(train)

    # Split off the untouched 15% acceptance holdout first.
    development_indices, holdout_indices = train_test_split(
        train.index,
        test_size=0.15,
        random_state=RANDOM_STATE,
        stratify=all_targets,
    )
    # 15/85 of the remaining data produces 15% of the complete training file.
    detector_indices, fusion_indices = train_test_split(
        development_indices,
        test_size=0.15 / 0.85,
        random_state=RANDOM_STATE,
        stratify=all_targets.loc[development_indices],
    )
    partition_sizes = {
        "detector_fitting": int(len(detector_indices)),
        "fusion_selection": int(len(fusion_indices)),
        "acceptance_holdout": int(len(holdout_indices)),
    }
    if sum(partition_sizes.values()) != len(train):
        raise ValueError("Training-only partitions do not cover every training row.")

    detector_features = all_features.loc[detector_indices]
    detector_targets = all_targets.loc[detector_indices]
    fusion_features = all_features.loc[fusion_indices]
    fusion_targets = all_targets.loc[fusion_indices]
    fusion_families = (
        normalize_labels(train.loc[fusion_indices, LABEL_COLUMN])
        .map(get_attack_family)
    )
    normal_detector_features = detector_features[detector_targets == 0]

    durations: dict[str, float] = {}
    rf_pipeline = build_rf_pipeline()
    started = perf_counter()
    rf_pipeline.fit(detector_features, detector_targets)
    durations["initial_rf_training"] = perf_counter() - started

    if_pipeline = build_if_pipeline()
    started = perf_counter()
    if_pipeline.fit(normal_detector_features)
    durations["initial_if_training"] = perf_counter() - started

    started = perf_counter()
    calibration_lower, calibration_upper = calculate_calibration_bounds(
        if_pipeline, normal_detector_features
    )
    durations["initial_anomaly_calibration"] = perf_counter() - started

    rf_feature_count = len(
        rf_pipeline.named_steps["preprocessor"].get_feature_names_out()
    )
    if_feature_count = len(
        if_pipeline.named_steps["preprocessor"].get_feature_names_out()
    )

    started = perf_counter()
    fusion_rf_probabilities = rf_attack_probabilities(
        rf_pipeline, fusion_features
    )
    durations["fusion_rf_prediction"] = perf_counter() - started
    started = perf_counter()
    fusion_if_scores = calibrate_anomaly_scores(
        raw_anomaly_scores(if_pipeline, fusion_features),
        calibration_lower,
        calibration_upper,
    )
    durations["fusion_if_prediction_and_calibration"] = (
        perf_counter() - started
    )

    search_started = perf_counter()
    search_rows: list[dict[str, Any]] = []
    for rf_weight in RF_WEIGHTS:
        if_weight = 1.0 - rf_weight
        hybrid_scores = (
            rf_weight * fusion_rf_probabilities
            + if_weight * fusion_if_scores
        )
        for threshold in THRESHOLDS:
            metrics, _ = calculate_metrics(
                fusion_targets,
                hybrid_scores,
                float(threshold),
                fusion_families,
            )
            search_rows.append(
                {
                    "rf_weight": rf_weight,
                    "if_weight": if_weight,
                    **metrics,
                    "meets_fpr_constraint": (
                        metrics["false_positive_rate"] <= FPR_LIMIT
                    ),
                }
            )
    selected_fusion, constrained_choice_available = choose_fusion(search_rows)
    for row in search_rows:
        row["selected"] = (
            row["rf_weight"] == selected_fusion["rf_weight"]
            and row["threshold"] == selected_fusion["threshold"]
        )
    durations["fusion_grid_evaluation"] = perf_counter() - search_started
    pd.DataFrame(search_rows).to_csv(fusion_search_path, index=False)

    selection_report = {
        "data_source": TRAIN_FILENAME,
        "fusion_selection_rows": int(len(fusion_indices)),
        "rf_weights_evaluated": RF_WEIGHTS,
        "threshold_grid": {
            "minimum": 0.10,
            "maximum": 0.90,
            "increment": 0.01,
            "count_per_weight": len(THRESHOLDS),
        },
        "false_positive_rate_limit": FPR_LIMIT,
        "valid_constrained_combination_available": (
            constrained_choice_available
        ),
        "selection_policy": (
            "Prefer FPR <= 0.05; maximize F2, then recall, macro attack-family "
            "recall, lower FPR, precision, RF weight closest to 0.70, and "
            "threshold closest to 0.50."
        ),
        "selected_fusion": selected_fusion,
        "official_test_data_used": False,
        "internal_holdout_data_used": False,
    }
    write_json(selection_path, selection_report)

    # Only now, after fusion is locked, evaluate the untouched acceptance holdout.
    holdout_features = all_features.loc[holdout_indices]
    holdout_targets = all_targets.loc[holdout_indices]
    holdout_families = (
        normalize_labels(train.loc[holdout_indices, LABEL_COLUMN])
        .map(get_attack_family)
    )
    started = perf_counter()
    holdout_rf_probabilities = rf_attack_probabilities(
        rf_pipeline, holdout_features
    )
    durations["holdout_rf_prediction"] = perf_counter() - started
    started = perf_counter()
    holdout_if_scores = calibrate_anomaly_scores(
        raw_anomaly_scores(if_pipeline, holdout_features),
        calibration_lower,
        calibration_upper,
    )
    durations["holdout_if_prediction_and_calibration"] = (
        perf_counter() - started
    )
    holdout_hybrid_scores = (
        selected_fusion["rf_weight"] * holdout_rf_probabilities
        + selected_fusion["if_weight"] * holdout_if_scores
    )
    rf_holdout_metrics, _ = calculate_metrics(
        holdout_targets,
        holdout_rf_probabilities,
        RF_ONLY_THRESHOLD,
        holdout_families,
    )
    hybrid_holdout_metrics, _ = calculate_metrics(
        holdout_targets,
        holdout_hybrid_scores,
        selected_fusion["threshold"],
        holdout_families,
    )
    accepted = (
        hybrid_holdout_metrics["false_positive_rate"] <= FPR_LIMIT
        and hybrid_holdout_metrics["f2"] > rf_holdout_metrics["f2"]
    )
    outcome = "accepted" if accepted else "rejected"
    if accepted:
        decision_reason = (
            "Accepted because holdout hybrid FPR was <= 0.05 and holdout "
            "hybrid F2 was strictly higher than frozen RF-only F2."
        )
    else:
        failed_conditions: list[str] = []
        if hybrid_holdout_metrics["false_positive_rate"] > FPR_LIMIT:
            failed_conditions.append(
                "holdout hybrid FPR exceeded the 0.05 limit"
            )
        if hybrid_holdout_metrics["f2"] <= rf_holdout_metrics["f2"]:
            failed_conditions.append(
                "holdout hybrid F2 was not strictly higher than RF-only F2"
            )
        decision_reason = "Rejected because " + " and ".join(failed_conditions) + "."

    holdout_frame = pd.DataFrame(
        [
            internal_comparison_row(
                "N2.1 Random Forest only",
                1.0,
                0.0,
                rf_holdout_metrics,
            ),
            internal_comparison_row(
                "selected hybrid",
                selected_fusion["rf_weight"],
                selected_fusion["if_weight"],
                hybrid_holdout_metrics,
            ),
        ]
    )
    holdout_frame["experiment_outcome"] = outcome
    holdout_frame.to_csv(holdout_path, index=False)

    official_metrics: dict[str, Any] | None = None
    test_only_summary: dict[str, Any] | None = None
    artifact_size: int | None = None
    artifact_hash: str | None = None
    final_calibration: dict[str, float] | None = None
    accepted_report_paths: list[Path] = []
    mapped_test_labels: list[str] | None = None

    if accepted:
        # Refit both components from scratch using their full-data policies.
        final_rf_pipeline = build_rf_pipeline()
        started = perf_counter()
        final_rf_pipeline.fit(all_features, all_targets)
        durations["final_rf_full_training"] = perf_counter() - started

        all_normal_features = all_features[all_targets == 0]
        final_if_pipeline = build_if_pipeline()
        started = perf_counter()
        final_if_pipeline.fit(all_normal_features)
        durations["final_if_normal_training"] = perf_counter() - started
        started = perf_counter()
        final_lower, final_upper = calculate_calibration_bounds(
            final_if_pipeline, all_normal_features
        )
        durations["final_anomaly_calibration"] = perf_counter() - started
        final_calibration = {"lower": final_lower, "upper": final_upper}

        # Official test data is loaded only after the acceptance decision.
        test = load_complete_nsl_kdd(test_path)
        mapped_test_labels = validate_label_mapping(test, TEST_FILENAME)
        test_features, test_targets = split_features_and_target(test)
        test_families = normalize_labels(test[LABEL_COLUMN]).map(
            get_attack_family
        )
        started = perf_counter()
        test_rf_probabilities = rf_attack_probabilities(
            final_rf_pipeline, test_features
        )
        durations["official_test_rf_prediction"] = perf_counter() - started
        started = perf_counter()
        test_if_scores = calibrate_anomaly_scores(
            raw_anomaly_scores(final_if_pipeline, test_features),
            final_lower,
            final_upper,
        )
        durations["official_test_if_prediction_and_calibration"] = (
            perf_counter() - started
        )
        test_hybrid_scores = (
            selected_fusion["rf_weight"] * test_rf_probabilities
            + selected_fusion["if_weight"] * test_if_scores
        )
        official_metrics, official_predictions = calculate_metrics(
            test_targets,
            test_hybrid_scores,
            selected_fusion["threshold"],
            test_families,
            include_ranking_metrics=True,
        )
        official_family_report = build_family_report(
            test, official_predictions
        )
        test_only_report, test_only_summary = build_test_only_label_report(
            train, test, official_predictions
        )

        official_report = {
            "experiment_outcome": outcome,
            "selected_rf_weight": selected_fusion["rf_weight"],
            "selected_if_weight": selected_fusion["if_weight"],
            "selected_threshold": selected_fusion["threshold"],
            "complete_official_test_rows": int(len(test)),
            "official_test_metrics": official_metrics,
            "test_only_attack_label_performance": test_only_summary,
            "selection_parameters_revised_after_test": False,
        }
        write_json(official_metrics_path, official_report)
        pd.DataFrame(
            [
                {
                    "actual": "normal",
                    "predicted_normal": official_metrics["true_negatives"],
                    "predicted_attack": official_metrics[
                        "false_positives"
                    ],
                },
                {
                    "actual": "attack",
                    "predicted_normal": official_metrics[
                        "false_negatives"
                    ],
                    "predicted_attack": official_metrics["true_positives"],
                },
            ]
        ).to_csv(official_confusion_path, index=False)
        official_family_report.to_csv(official_family_path, index=False)
        test_only_report.to_csv(test_only_path, index=False)

        baseline_metrics = json.loads(
            (reports_directory / "binary_classifier_metrics.json").read_text(
                encoding="utf-8"
            )
        )
        improved_metrics = json.loads(
            (reports_directory / "improved_binary_metrics.json").read_text(
                encoding="utf-8"
            )
        )
        baseline_families = pd.read_csv(
            reports_directory / "attack_family_detection.csv"
        )
        improved_families = pd.read_csv(
            reports_directory / "improved_attack_family_detection.csv"
        )
        comparison_rows = [
            historical_comparison_row(
                "N2",
                "baseline Random Forest",
                0.5,
                baseline_metrics["test_metrics"],
                baseline_families,
                phase_n2=True,
            ),
            historical_comparison_row(
                "N2.1",
                "improved Random Forest",
                0.38,
                improved_metrics[
                    "official_test_metrics_selected_threshold"
                ],
                improved_families,
            ),
            hybrid_comparison_row(
                selected_fusion["threshold"], official_metrics
            ),
        ]
        pd.DataFrame(comparison_rows).to_csv(three_way_path, index=False)

        artifact_content = {
            "random_forest_pipeline": final_rf_pipeline,
            "isolation_forest_pipeline": final_if_pipeline,
            "random_forest_weight": selected_fusion["rf_weight"],
            "isolation_forest_weight": selected_fusion["if_weight"],
            "hybrid_threshold": selected_fusion["threshold"],
            "anomaly_calibration_lower_bound": final_lower,
            "anomaly_calibration_upper_bound": final_upper,
            "feature_columns": INCLUDED_FEATURE_COLUMNS,
            "categorical_columns": CATEGORICAL_COLUMNS,
            "excluded_columns": EXCLUDED_COLUMNS,
            "target_mapping": {"normal": 0, "attack": 1},
            "model_versions_and_configurations": {
                "scikit_learn_version": sklearn.__version__,
                "random_forest": RF_PARAMETERS,
                "isolation_forest": IF_PARAMETERS,
                "anomaly_numeric_scaler": "StandardScaler(with_mean=False)",
                "anomaly_calibration": (
                    "normal-fit raw score 1st/99th percentile clipping"
                ),
            },
        }
        joblib.dump(artifact_content, artifact_path, compress=3)
        artifact_size = artifact_path.stat().st_size
        artifact_hash = sha256_file(artifact_path)
        accepted_report_paths = [
            official_metrics_path,
            official_confusion_path,
            official_family_path,
            test_only_path,
            three_way_path,
        ]

    split_policy = {
        "source": TRAIN_FILENAME,
        "random_state": RANDOM_STATE,
        "stratified_binary_target": True,
        "two_train_test_split_calls": True,
        "detector_fitting_fraction": 0.70,
        "fusion_selection_fraction": 0.15,
        "acceptance_holdout_fraction": 0.15,
        "partition_row_counts": partition_sizes,
        "sampling_or_synthetic_data_used": False,
    }
    isolation_policy = {
        "initial_fit_rows": int(len(normal_detector_features)),
        "initial_fit_source": (
            "normal-labelled records from detector fitting partition only"
        ),
        "parameters": IF_PARAMETERS,
        "preprocessing": {
            "categorical": "OneHotEncoder(handle_unknown='ignore')",
            "numeric": "StandardScaler(with_mean=False)",
        },
        "attack_records_used_for_fit": False,
    }
    calibration_method = {
        "raw_score": "-IsolationForest.decision_function(X)",
        "initial_lower_1st_percentile": calibration_lower,
        "initial_upper_99th_percentile": calibration_upper,
        "fit_source": "normal records used for initial Isolation Forest fit",
        "transformation": (
            "clip((raw_score - lower) / (upper - lower), 0, 1)"
        ),
        "final_full_normal_training_bounds": final_calibration,
    }
    acceptance_record = {
        "decision": outcome,
        "reason": decision_reason,
        "required_fpr_maximum": FPR_LIMIT,
        "required_strict_f2_improvement": True,
        "rf_only_holdout_f2": rf_holdout_metrics["f2"],
        "hybrid_holdout_f2": hybrid_holdout_metrics["f2"],
        "hybrid_holdout_false_positive_rate": hybrid_holdout_metrics[
            "false_positive_rate"
        ],
        "parameters_changed_after_holdout": False,
    }
    report_paths = {
        "fusion_search": relative_path(fusion_search_path, root),
        "fusion_selection": relative_path(selection_path, root),
        "internal_holdout_comparison": relative_path(holdout_path, root),
        "experiment_summary": relative_path(summary_path, root),
        "metadata": relative_path(metadata_path, root),
    }
    if accepted:
        report_paths.update(
            {
                "official_test_metrics": relative_path(
                    official_metrics_path, root
                ),
                "official_confusion_matrix": relative_path(
                    official_confusion_path, root
                ),
                "official_family_detection": relative_path(
                    official_family_path, root
                ),
                "test_only_label_detection": relative_path(
                    test_only_path, root
                ),
                "three_way_comparison": relative_path(three_way_path, root),
            }
        )

    summary = {
        "experiment_outcome": outcome,
        "decision_reason": decision_reason,
        "split_policy": split_policy,
        "feature_policy": {
            "input_feature_count": len(INCLUDED_FEATURE_COLUMNS),
            "categorical_feature_count": len(CATEGORICAL_COLUMNS),
            "numeric_feature_count": len(INCLUDED_NUMERIC_COLUMNS),
            "excluded_columns": EXCLUDED_COLUMNS,
            "initial_rf_transformed_feature_count": rf_feature_count,
            "initial_if_transformed_feature_count": if_feature_count,
        },
        "isolation_forest_training_policy": isolation_policy,
        "anomaly_calibration_method": calibration_method,
        "selected_fusion": selected_fusion,
        "fusion_selection_constraint_available": (
            constrained_choice_available
        ),
        "internal_holdout": {
            "rf_only_threshold": RF_ONLY_THRESHOLD,
            "rf_only_metrics": rf_holdout_metrics,
            "hybrid_metrics": hybrid_holdout_metrics,
            "acceptance": acceptance_record,
        },
        "official_test_metrics": official_metrics,
        "test_only_attack_label_performance": test_only_summary,
        "durations_seconds": durations,
        "official_test_loaded": accepted,
        "official_test_influenced_selection": False,
        "selection_revised_after_official_test": False,
        "report_paths": report_paths,
    }
    write_json(summary_path, summary)

    metadata: dict[str, Any] = {
        "project_model_name": "Athes Sentinel controlled hybrid detector experiment",
        "experiment_outcome": outcome,
        "split_policy": split_policy,
        "random_forest_training_policy": {
            "initial_fit_source": "70% detector fitting partition",
            "parameters": RF_PARAMETERS,
            "frozen_rf_only_threshold": RF_ONLY_THRESHOLD,
        },
        "isolation_forest_training_policy": isolation_policy,
        "anomaly_calibration_method": calibration_method,
        "selected_fusion_weight": {
            "random_forest": selected_fusion["rf_weight"],
            "isolation_forest": selected_fusion["if_weight"],
        },
        "selected_fusion_threshold": selected_fusion["threshold"],
        "fusion_selection_metrics": selected_fusion,
        "internal_holdout_comparison": {
            "rf_only": rf_holdout_metrics,
            "hybrid": hybrid_holdout_metrics,
        },
        "acceptance_decision": acceptance_record,
        "official_test_metrics": official_metrics,
        "artifact_saved": accepted,
        "scikit_learn_version": sklearn.__version__,
        "creation_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "all_training_labels_mapped": True,
        "mapped_training_labels": mapped_train_labels,
        "all_test_labels_mapped": True if accepted else None,
        "mapped_test_labels": mapped_test_labels,
        "official_test_data_did_not_influence_model_or_fusion_selection": True,
        "official_test_loaded_only_after_acceptance": accepted,
        "selection_statement": (
            "The RF/IF models, anomaly calibration, fusion weight, and fusion "
            "threshold were fixed without official-test data. No official-test "
            "result was used to revise them."
        ),
    }
    if accepted:
        metadata.update(
            {
                "artifact_path": relative_path(artifact_path, root),
                "artifact_size_bytes": artifact_size,
                "artifact_sha256": artifact_hash,
            }
        )
    write_json(metadata_path, metadata)

    always_report_paths = [
        fusion_search_path,
        selection_path,
        holdout_path,
        summary_path,
        metadata_path,
    ]
    print_summary(
        partition_sizes,
        int(len(normal_detector_features)),
        rf_feature_count,
        if_feature_count,
        {"lower": calibration_lower, "upper": calibration_upper},
        selected_fusion,
        rf_holdout_metrics,
        hybrid_holdout_metrics,
        outcome,
        durations,
        always_report_paths,
        official_metrics=official_metrics,
        test_only_summary=test_only_summary,
        artifact_path=artifact_path if accepted else None,
        artifact_hash=artifact_hash,
        accepted_report_paths=accepted_report_paths,
    )


if __name__ == "__main__":
    main()
