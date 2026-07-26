"""Loading and preprocessing helpers for the complete NSL-KDD datasets."""

from __future__ import annotations

import inspect
from pathlib import Path

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder

from ml_pipeline.nsl_kdd_schema import (
    ALL_COLUMNS,
    CATEGORICAL_COLUMNS,
    DIFFICULTY_COLUMN,
    FEATURE_COLUMNS,
    LABEL_COLUMN,
    NUMERIC_FEATURE_COLUMNS,
)

EXPECTED_COLUMN_COUNT = 43
CONSTANT_COLUMN = "num_outbound_cmds"
EXCLUDED_COLUMNS = [LABEL_COLUMN, DIFFICULTY_COLUMN, CONSTANT_COLUMN]
INCLUDED_FEATURE_COLUMNS = [
    column for column in FEATURE_COLUMNS if column != CONSTANT_COLUMN
]
INCLUDED_NUMERIC_COLUMNS = [
    column for column in NUMERIC_FEATURE_COLUMNS if column != CONSTANT_COLUMN
]


def load_complete_nsl_kdd(path: Path) -> pd.DataFrame:
    """Load every row from a complete headerless NSL-KDD text file."""
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


def normalize_labels(labels: pd.Series) -> pd.Series:
    """Normalize labels without changing the source DataFrame."""
    return (
        labels.astype(str)
        .str.strip()
        .str.lower()
        .str.removesuffix(".")
    )


def create_binary_targets(labels: pd.Series) -> pd.Series:
    """Map normal to 0 and every attack label to 1."""
    normalized = normalize_labels(labels)
    return normalized.ne("normal").astype("int8").rename("is_attack")


def validate_excluded_columns(features: pd.DataFrame) -> None:
    """Ensure target, difficulty, and constant columns cannot leak into training."""
    unexpected_excluded = [
        column for column in EXCLUDED_COLUMNS if column in features.columns
    ]
    if unexpected_excluded:
        raise ValueError(
            "Excluded columns are present in the feature matrix: "
            f"{unexpected_excluded}"
        )
    if list(features.columns) != INCLUDED_FEATURE_COLUMNS:
        raise ValueError(
            "Feature columns do not match the expected 40-column feature policy."
        )


def split_features_and_target(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Series]:
    """Create an independent 40-feature matrix and binary target series."""
    features = frame.loc[:, INCLUDED_FEATURE_COLUMNS].copy()
    target = create_binary_targets(frame[LABEL_COLUMN])
    validate_excluded_columns(features)
    return features, target


def build_preprocessor() -> ColumnTransformer:
    """Build an unfitted categorical encoder plus numeric pass-through."""
    encoder_parameters: dict[str, object] = {"handle_unknown": "ignore"}
    if "sparse_output" in inspect.signature(OneHotEncoder).parameters:
        encoder_parameters["sparse_output"] = True
    else:
        # Compatibility with scikit-learn releases older than 1.2.
        encoder_parameters["sparse"] = True

    return ColumnTransformer(
        transformers=[
            (
                "categorical",
                OneHotEncoder(**encoder_parameters),
                CATEGORICAL_COLUMNS,
            ),
            ("numeric", "passthrough", INCLUDED_NUMERIC_COLUMNS),
        ]
    )
