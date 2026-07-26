"""Pydantic response schemas for network dataset ingestion and reading."""

from datetime import datetime

from pydantic import BaseModel, create_model

from ml_pipeline.nsl_kdd_schema import (
    CATEGORICAL_COLUMNS,
    FEATURE_COLUMNS,
    NUMERIC_FEATURE_COLUMNS,
)


class DistributionValue(BaseModel):
    """One value and its number of uploaded records."""

    value: str
    count: int


class NetworkDatasetSummary(BaseModel):
    """Metadata shown in dataset listings."""

    id: int
    filename: str
    uploaded_at: datetime
    total_records: int
    has_ground_truth: bool
    source_type: str
    analysis_status: str
    analysis_error: str | None
    model_name: str | None
    model_threshold: float | None
    analysis_started_at: datetime | None
    analysis_completed_at: datetime | None


class NetworkDatasetUploadResponse(NetworkDatasetSummary):
    """Dataset metadata plus compact distributions calculated during upload."""

    label_distribution: list[DistributionValue]
    attack_family_distribution: list[DistributionValue]
    protocol_distribution: list[DistributionValue]
    service_unique_count: int
    flag_distribution: list[DistributionValue]


class PaginatedNetworkDatasets(BaseModel):
    """One page from the dataset listing."""

    items: list[NetworkDatasetSummary]
    total: int
    limit: int
    offset: int


class NetworkDatasetDetail(NetworkDatasetSummary):
    """Dataset metadata plus current analysis-related child counts."""

    stored_flow_count: int
    prediction_count: int
    incident_count: int
    predicted_normal_count: int
    predicted_attack_count: int


def _network_feature_response_fields() -> dict:
    """Build response fields from the official schema without duplicating it."""
    fields = {}
    for column in FEATURE_COLUMNS:
        if column in CATEGORICAL_COLUMNS:
            field_type = str
        elif column in NUMERIC_FEATURE_COLUMNS and column.endswith("_rate"):
            field_type = float
        else:
            field_type = int
        fields[column] = (field_type, ...)
    return fields


NetworkFlowResponse = create_model(
    "NetworkFlowResponse",
    id=(int, ...),
    dataset_id=(int, ...),
    row_number=(int, ...),
    **_network_feature_response_fields(),
    actual_label=(str | None, None),
    actual_family=(str | None, None),
    difficulty_level=(int | None, None),
)
NetworkFlowResponse.__doc__ = (
    "One stored source-order flow with all 41 original official features."
)
NetworkFlowResponse.__module__ = __name__


class PaginatedNetworkFlows(BaseModel):
    """One source-ordered page of stored network flows."""

    dataset_id: int
    items: list[NetworkFlowResponse]
    total: int
    limit: int
    offset: int
