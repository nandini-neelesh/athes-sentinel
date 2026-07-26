"""Pydantic response schemas for network dataset ingestion and reading."""

from datetime import datetime
from typing import Literal

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


class NetworkSeverityCounts(BaseModel):
    """Incident counts for the fixed product-triage severity bands."""

    critical: int
    high: int
    medium: int
    low: int


class NetworkBenchmarkMetrics(BaseModel):
    """Optional benchmark-only outcomes for a labelled uploaded dataset."""

    actual_normal: int
    actual_attack: int
    true_negatives: int
    false_positives: int
    false_negatives: int
    true_positives: int
    accuracy: float
    precision: float
    recall: float
    f1: float
    f2: float
    false_positive_rate: float
    false_negative_rate: float


class NetworkAnalysisResponse(BaseModel):
    """Persisted analysis state and aggregate detector outcomes."""

    dataset_id: int
    filename: str
    total_flows: int
    total_predictions: int
    predicted_normal: int
    predicted_attack: int
    predicted_attack_percentage: float
    total_incidents: int
    severity_counts: NetworkSeverityCounts
    minimum_probability: float | None
    maximum_probability: float | None
    mean_probability: float | None
    model_name: str | None
    model_version: str | None
    threshold: float | None
    analysis_status: str
    analysis_error: str | None
    analysis_started_at: datetime | None
    analysis_completed_at: datetime | None
    reused_existing: bool
    benchmark_metrics: NetworkBenchmarkMetrics | None


class NetworkDashboardDatasetInfo(BaseModel):
    """Source dataset and persisted analysis lifecycle information."""

    dataset_id: int
    filename: str
    uploaded_at: datetime
    total_flows: int
    has_ground_truth: bool
    source_type: str
    analysis_status: str
    analysis_error: str | None
    analysis_started_at: datetime | None
    analysis_completed_at: datetime | None


class NetworkDashboardModelInfo(BaseModel):
    """Frozen model identifier and real probability threshold."""

    model_name: str
    model_version: str
    threshold_probability: float


class NetworkPredictionKpis(BaseModel):
    """Persisted prediction totals and 0-1 probability statistics."""

    total_predictions: int
    predicted_normal: int
    predicted_attack: int
    predicted_attack_percentage: float
    minimum_attack_probability: float | None
    maximum_attack_probability: float | None
    mean_attack_probability: float | None


class NetworkIncidentKpis(BaseModel):
    """Analyst workflow, severity, and 0-100 risk-score totals."""

    total_incidents: int
    open_incidents: int
    investigating_incidents: int
    resolved_incidents: int
    false_positive_status_incidents: int
    critical_incidents: int
    high_incidents: int
    medium_incidents: int
    low_incidents: int
    highest_risk_score: float | None


class NetworkCompactIncident(BaseModel):
    """One joined incident row suitable for a queue or dashboard preview."""

    incident_id: int
    dataset_id: int
    flow_id: int
    prediction_id: int
    row_number: int
    created_at: datetime
    incident_type: str
    severity: str
    risk_score: float
    status: str
    protocol_type: str | None
    service: str | None
    flag: str | None
    actual_label: str | None
    actual_family: str | None
    rf_attack_probability: float
    evidence_preview: str


class NetworkDashboardResponse(BaseModel):
    """Complete persisted dashboard state without rerunning inference."""

    dataset: NetworkDashboardDatasetInfo
    model: NetworkDashboardModelInfo | None
    prediction_kpis: NetworkPredictionKpis
    incident_kpis: NetworkIncidentKpis
    benchmark_metrics: NetworkBenchmarkMetrics | None
    priority_incidents: list[NetworkCompactIncident]


class NetworkPredictionDistributionEntry(BaseModel):
    """Normal or attack prediction count with a 0-100 percentage."""

    predicted_class: str
    record_count: int
    percentage: float


class NetworkProtocolAnalyticsEntry(BaseModel):
    """Persisted detector outcomes grouped by original protocol."""

    protocol: str
    total_records: int
    predicted_attacks: int
    attack_percentage: float
    mean_attack_probability: float


class NetworkServiceAnalyticsEntry(BaseModel):
    """Persisted detector outcomes grouped by original service."""

    service: str
    total_records: int
    predicted_attacks: int
    attack_percentage: float
    mean_attack_probability: float
    maximum_attack_probability: float


class NetworkFlagAnalyticsEntry(BaseModel):
    """Persisted detector outcomes grouped by original connection flag."""

    flag: str
    total_records: int
    predicted_attacks: int
    attack_percentage: float
    mean_attack_probability: float


class NetworkProbabilityHistogramBucket(BaseModel):
    """One non-overlapping bucket of persisted 0-1 probabilities."""

    lower_bound_probability: float
    upper_bound_probability: float
    label: str
    record_count: int
    percentage: float


class NetworkNamedCount(BaseModel):
    """One fixed benchmark category and its record count."""

    value: str
    record_count: int


class NetworkAnalyticsResponse(BaseModel):
    """SQL-derived persisted network distributions for one dataset."""

    dataset_id: int
    analysis_status: str
    prediction_distribution: list[NetworkPredictionDistributionEntry]
    protocol_distribution: list[NetworkProtocolAnalyticsEntry]
    service_distribution: list[NetworkServiceAnalyticsEntry]
    flag_distribution: list[NetworkFlagAnalyticsEntry]
    severity_distribution: NetworkSeverityCounts
    probability_histogram: list[NetworkProbabilityHistogramBucket]
    actual_family_distribution: list[NetworkNamedCount] | None
    correctness_distribution: list[NetworkNamedCount] | None
    benchmark_metrics: NetworkBenchmarkMetrics | None


class NetworkIncidentQueueFilters(BaseModel):
    """Echo the active database-supported incident filters."""

    status: str | None
    severity: str | None
    search: str | None


class PaginatedNetworkIncidents(BaseModel):
    """One risk-ordered, filtered page of joined network incidents."""

    dataset_id: int
    items: list[NetworkCompactIncident]
    total: int
    limit: int
    offset: int
    filters: NetworkIncidentQueueFilters


class NetworkIncidentPredictionDetail(BaseModel):
    """Persisted frozen-model values linked to an incident."""

    rf_attack_probability: float
    predicted_class: str
    threshold_used_probability: float
    model_name: str
    model_version: str
    actual_binary: int | None
    is_correct: bool | None


class NetworkIncidentFlowContext(BaseModel):
    """Useful original flow values without encoded or fabricated fields."""

    row_number: int
    duration: int
    protocol_type: str
    service: str
    flag: str
    src_bytes: int
    dst_bytes: int
    num_failed_logins: int
    logged_in: int
    count: int
    srv_count: int
    serror_rate: float
    srv_serror_rate: float
    rerror_rate: float
    srv_rerror_rate: float
    same_srv_rate: float
    diff_srv_rate: float
    srv_diff_host_rate: float
    dst_host_count: int
    dst_host_srv_count: int
    dst_host_same_srv_rate: float
    dst_host_diff_srv_rate: float
    dst_host_same_src_port_rate: float
    dst_host_srv_diff_host_rate: float
    dst_host_serror_rate: float
    dst_host_srv_serror_rate: float
    dst_host_rerror_rate: float
    dst_host_srv_rerror_rate: float
    actual_label: str | None
    actual_family: str | None
    difficulty_level: int | None


class NetworkIncidentDetail(NetworkCompactIncident):
    """Full incident, prediction, and real source-flow context."""

    evidence: str
    recommended_action: str
    prediction: NetworkIncidentPredictionDetail
    flow_context: NetworkIncidentFlowContext


class NetworkIncidentStatusUpdate(BaseModel):
    """The only mutable analyst workflow field in N4D."""

    status: Literal["open", "investigating", "resolved", "false_positive"]


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
