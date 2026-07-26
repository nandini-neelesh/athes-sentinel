"""Inspect the complete NSL-KDD train and test files without modifying them."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ml_pipeline.nsl_kdd_schema import (
    ALL_COLUMNS,
    CATEGORICAL_COLUMNS,
    DIFFICULTY_COLUMN,
    LABEL_COLUMN,
    NUMERIC_FEATURE_COLUMNS,
)

EXPECTED_COLUMN_COUNT = 43
DATASET_DIRECTORY = Path("data") / "external" / "nsl-kdd"
TRAIN_FILENAME = "KDDTrain+.txt"
TEST_FILENAME = "KDDTest+.txt"


def repository_root() -> Path:
    """Resolve the repository root relative to this module."""
    return Path(__file__).resolve().parent.parent


def load_dataset(path: Path) -> pd.DataFrame:
    """Read every row and validate the headerless file before naming columns."""
    if not path.is_file():
        raise FileNotFoundError(f"Required NSL-KDD dataset file not found: {path}")

    frame = pd.read_csv(path, header=None, delimiter=",")
    observed_columns = frame.shape[1]
    if observed_columns != EXPECTED_COLUMN_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_COLUMN_COUNT} columns in {path}, "
            f"but observed {observed_columns}."
        )

    frame.columns = ALL_COLUMNS
    return frame


def normalized_labels(frame: pd.DataFrame) -> pd.Series:
    """Return reporting-only normalized labels, leaving the raw column intact."""
    return (
        frame[LABEL_COLUMN]
        .astype(str)
        .str.strip()
        .str.lower()
        .str.removesuffix(".")
    )


def sorted_values(series: pd.Series) -> list[Any]:
    """Convert sorted pandas values to JSON-friendly Python values."""
    return [value.item() if hasattr(value, "item") else value for value in sorted(series)]


def dataset_report(frame: pd.DataFrame, source_path: Path) -> dict[str, Any]:
    """Calculate factual structural and distribution statistics."""
    labels = normalized_labels(frame)
    label_counts = labels.value_counts()
    missing_counts = frame.isna().sum()
    numeric_columns = NUMERIC_FEATURE_COLUMNS + [DIFFICULTY_COLUMN]
    numeric_frame = frame[numeric_columns]
    infinity_count = int(np.isinf(numeric_frame.to_numpy(dtype=float)).sum())
    normal_count = int(label_counts.get("normal", 0))
    constant_columns = [
        column for column in ALL_COLUMNS if frame[column].nunique(dropna=False) == 1
    ]
    zero_variance_columns = [
        column
        for column in numeric_columns
        if frame[column].var(ddof=0) == 0
    ]

    return {
        "source_filename": source_path.name,
        "file_size_bytes": source_path.stat().st_size,
        "row_count": int(frame.shape[0]),
        "column_count": int(frame.shape[1]),
        "duplicate_row_count": int(frame.duplicated().sum()),
        "total_missing_cell_count": int(missing_counts.sum()),
        "missing_count_per_column_nonzero": {
            column: int(count)
            for column, count in missing_counts.items()
            if count > 0
        },
        "positive_infinity_count_numeric_columns": int(
            np.isposinf(numeric_frame.to_numpy(dtype=float)).sum()
        ),
        "negative_infinity_count_numeric_columns": int(
            np.isneginf(numeric_frame.to_numpy(dtype=float)).sum()
        ),
        "infinity_count_numeric_columns": infinity_count,
        "memory_usage_bytes": int(frame.memory_usage(index=True, deep=True).sum()),
        "categorical_unique_counts": {
            column: int(frame[column].nunique(dropna=False))
            for column in CATEGORICAL_COLUMNS
        },
        "normalized_label_distribution": {
            label: int(count) for label, count in label_counts.items()
        },
        "number_of_unique_labels": int(labels.nunique()),
        "binary_distribution": {
            "normal": normal_count,
            "attack": int(len(frame) - normal_count),
        },
        "difficulty_level_minimum": int(frame[DIFFICULTY_COLUMN].min()),
        "difficulty_level_maximum": int(frame[DIFFICULTY_COLUMN].max()),
        "columns_containing_one_unique_value": constant_columns,
        "numeric_columns_with_zero_variance": zero_variance_columns,
    }


def comparison_report(
    train: pd.DataFrame, test: pd.DataFrame
) -> dict[str, Any]:
    """Compare raw categorical domains and normalized labels."""
    train_labels = set(normalized_labels(train).unique())
    test_labels = set(normalized_labels(test).unique())
    comparison: dict[str, Any] = {
        "labels_appearing_only_in_training": sorted(train_labels - test_labels),
        "labels_appearing_only_in_testing": sorted(test_labels - train_labels),
        "same_43_column_structure": (
            list(train.columns) == list(test.columns) == ALL_COLUMNS
            and train.shape[1] == test.shape[1] == EXPECTED_COLUMN_COUNT
        ),
    }
    for column in CATEGORICAL_COLUMNS:
        train_values = set(train[column].dropna().unique())
        test_values = set(test[column].dropna().unique())
        comparison[f"{column}_values_appearing_only_in_testing"] = sorted_values(
            pd.Series(list(test_values - train_values), dtype=object)
        )
    return comparison


def write_label_distribution(
    labels: pd.Series, output_path: Path
) -> None:
    """Write a descending full-dataset label distribution."""
    counts = labels.value_counts().rename_axis("label").reset_index(name="count")
    counts["percentage"] = counts["count"] / len(labels) * 100
    counts.to_csv(output_path, index=False)


def print_summary(
    train: pd.DataFrame,
    test: pd.DataFrame,
    report: dict[str, Any],
    generated_paths: list[Path],
) -> None:
    """Print only the key inspection outcomes and output locations."""
    train_report = report["train"]
    test_report = report["test"]
    comparison = report["train_vs_test"]
    print(f"Train shape: {train.shape}")
    print(f"Test shape: {test.shape}")
    print(f"Train normal/attack: {train_report['binary_distribution']}")
    print(f"Test normal/attack: {test_report['binary_distribution']}")
    print(f"Train unique labels: {train_report['number_of_unique_labels']}")
    print(f"Test unique labels: {test_report['number_of_unique_labels']}")
    print(f"Labels only in test: {comparison['labels_appearing_only_in_testing']}")
    print(
        "Duplicate rows (train/test): "
        f"{train_report['duplicate_row_count']}/{test_report['duplicate_row_count']}"
    )
    print(
        "Missing cells (train/test): "
        f"{train_report['total_missing_cell_count']}/"
        f"{test_report['total_missing_cell_count']}"
    )
    print(
        "Infinities (train/test): "
        f"{train_report['infinity_count_numeric_columns']}/"
        f"{test_report['infinity_count_numeric_columns']}"
    )
    print("Generated reports:")
    for path in generated_paths:
        print(f"  {path}")


def main() -> None:
    """Load, inspect, compare, and report the two complete datasets."""
    root = repository_root()
    train_path = root / DATASET_DIRECTORY / TRAIN_FILENAME
    test_path = root / DATASET_DIRECTORY / TEST_FILENAME
    train = load_dataset(train_path)
    test = load_dataset(test_path)

    reports_directory = Path(__file__).resolve().parent / "reports"
    reports_directory.mkdir(parents=True, exist_ok=True)
    json_path = reports_directory / "nsl_kdd_dataset_report.json"
    train_csv_path = reports_directory / "train_label_distribution.csv"
    test_csv_path = reports_directory / "test_label_distribution.csv"

    report = {
        "train": dataset_report(train, train_path),
        "test": dataset_report(test, test_path),
        "train_vs_test": comparison_report(train, test),
    }
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_label_distribution(normalized_labels(train), train_csv_path)
    write_label_distribution(normalized_labels(test), test_csv_path)
    print_summary(
        train, test, report, [json_path, train_csv_path, test_csv_path]
    )


if __name__ == "__main__":
    main()
