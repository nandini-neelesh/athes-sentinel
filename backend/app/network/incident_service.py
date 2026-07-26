"""Persisted network-incident queue, detail, and workflow updates."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import or_

from backend.app.database.network_models import (
    NetworkDataset,
    NetworkFlow,
    NetworkIncident,
    NetworkPrediction,
)

LOGGER = logging.getLogger(__name__)
ALLOWED_INCIDENT_STATUSES = {
    "open",
    "investigating",
    "resolved",
    "false_positive",
}
ALLOWED_INCIDENT_SEVERITIES = {"critical", "high", "medium", "low"}
EVIDENCE_PREVIEW_LENGTH = 180


class NetworkIncidentPersistenceError(RuntimeError):
    """Raised after an incident status change is rolled back."""


def _evidence_preview(evidence: str) -> str:
    """Create a compact single-line preview without changing stored evidence."""
    compact = " ".join(evidence.split())
    if len(compact) <= EVIDENCE_PREVIEW_LENGTH:
        return compact
    return compact[: EVIDENCE_PREVIEW_LENGTH - 3].rstrip() + "..."


def compact_incident_row(
    incident: NetworkIncident,
    prediction: NetworkPrediction,
    flow: NetworkFlow,
) -> dict[str, Any]:
    """Format one already-joined queue row without triggering lazy queries."""
    return {
        "incident_id": incident.id,
        "dataset_id": incident.dataset_id,
        "flow_id": incident.flow_id,
        "prediction_id": incident.prediction_id,
        "row_number": flow.row_number,
        "created_at": incident.created_at,
        "incident_type": incident.incident_type,
        "severity": incident.severity,
        "risk_score": float(incident.risk_score),
        "status": incident.status,
        "protocol_type": incident.protocol_type,
        "service": incident.service,
        "flag": incident.flag,
        "actual_label": incident.actual_label,
        "actual_family": incident.actual_family,
        "rf_attack_probability": float(
            prediction.rf_attack_probability
        ),
        "evidence_preview": _evidence_preview(incident.evidence),
    }


def _joined_incident_query(db):
    """Build the explicit three-table join shared by queue and detail reads."""
    return (
        db.query(NetworkIncident, NetworkPrediction, NetworkFlow)
        .join(
            NetworkPrediction,
            NetworkPrediction.id == NetworkIncident.prediction_id,
        )
        .join(NetworkFlow, NetworkFlow.id == NetworkIncident.flow_id)
    )


def _validate_optional_filter(
    value: str | None,
    allowed_values: set[str],
    field_name: str,
) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized not in allowed_values:
        allowed = ", ".join(sorted(allowed_values))
        raise ValueError(
            f"Invalid network incident {field_name}. Allowed values: {allowed}."
        )
    return normalized


def _escaped_search_pattern(search: str) -> tuple[str | None, str | None]:
    """Normalize search and escape SQL wildcard characters."""
    normalized = search.strip()
    if not normalized:
        return None, None
    escaped = (
        normalized.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    return normalized, f"%{escaped}%"


def list_network_incidents(
    db,
    dataset_id: int,
    *,
    limit: int,
    offset: int,
    status: str | None = None,
    severity: str | None = None,
    search: str | None = None,
) -> dict[str, Any] | None:
    """Return one bounded page using database-side filters and one joined query."""
    if db.get(NetworkDataset, dataset_id) is None:
        return None
    normalized_status = _validate_optional_filter(
        status, ALLOWED_INCIDENT_STATUSES, "status"
    )
    normalized_severity = _validate_optional_filter(
        severity, ALLOWED_INCIDENT_SEVERITIES, "severity"
    )
    normalized_search, search_pattern = _escaped_search_pattern(search or "")

    query = _joined_incident_query(db).filter(
        NetworkIncident.dataset_id == dataset_id
    )
    if normalized_status is not None:
        query = query.filter(NetworkIncident.status == normalized_status)
    if normalized_severity is not None:
        query = query.filter(NetworkIncident.severity == normalized_severity)
    if search_pattern is not None:
        searchable_columns = [
            NetworkIncident.incident_type,
            NetworkIncident.protocol_type,
            NetworkIncident.service,
            NetworkIncident.flag,
            NetworkIncident.actual_label,
            NetworkIncident.actual_family,
        ]
        query = query.filter(
            or_(
                *[
                    column.ilike(search_pattern, escape="\\")
                    for column in searchable_columns
                ]
            )
        )

    total = int(query.count())
    rows = (
        query.order_by(
            NetworkIncident.risk_score.desc(),
            NetworkIncident.created_at.asc(),
            NetworkIncident.id.asc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "dataset_id": dataset_id,
        "items": [
            compact_incident_row(incident, prediction, flow)
            for incident, prediction, flow in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
        "filters": {
            "status": normalized_status,
            "severity": normalized_severity,
            "search": normalized_search,
        },
    }


def get_network_incident_detail(
    db, incident_id: int
) -> dict[str, Any] | None:
    """Return full persisted incident, prediction, and original flow context."""
    row = (
        _joined_incident_query(db)
        .filter(NetworkIncident.id == incident_id)
        .first()
    )
    if row is None:
        return None
    incident, prediction, flow = row
    return {
        **compact_incident_row(incident, prediction, flow),
        "evidence": incident.evidence,
        "recommended_action": incident.recommended_action,
        "prediction": {
            "rf_attack_probability": float(
                prediction.rf_attack_probability
            ),
            "predicted_class": prediction.predicted_class,
            "threshold_used_probability": float(prediction.threshold_used),
            "model_name": prediction.model_name,
            "model_version": prediction.model_version,
            "actual_binary": prediction.actual_binary,
            "is_correct": prediction.is_correct,
        },
        "flow_context": {
            "row_number": flow.row_number,
            "duration": flow.duration,
            "protocol_type": flow.protocol_type,
            "service": flow.service,
            "flag": flow.flag,
            "src_bytes": flow.src_bytes,
            "dst_bytes": flow.dst_bytes,
            "num_failed_logins": flow.num_failed_logins,
            "logged_in": flow.logged_in,
            "count": flow.count,
            "srv_count": flow.srv_count,
            "serror_rate": float(flow.serror_rate),
            "srv_serror_rate": float(flow.srv_serror_rate),
            "rerror_rate": float(flow.rerror_rate),
            "srv_rerror_rate": float(flow.srv_rerror_rate),
            "same_srv_rate": float(flow.same_srv_rate),
            "diff_srv_rate": float(flow.diff_srv_rate),
            "srv_diff_host_rate": float(flow.srv_diff_host_rate),
            "dst_host_count": flow.dst_host_count,
            "dst_host_srv_count": flow.dst_host_srv_count,
            "dst_host_same_srv_rate": float(
                flow.dst_host_same_srv_rate
            ),
            "dst_host_diff_srv_rate": float(
                flow.dst_host_diff_srv_rate
            ),
            "dst_host_same_src_port_rate": float(
                flow.dst_host_same_src_port_rate
            ),
            "dst_host_srv_diff_host_rate": float(
                flow.dst_host_srv_diff_host_rate
            ),
            "dst_host_serror_rate": float(
                flow.dst_host_serror_rate
            ),
            "dst_host_srv_serror_rate": float(
                flow.dst_host_srv_serror_rate
            ),
            "dst_host_rerror_rate": float(
                flow.dst_host_rerror_rate
            ),
            "dst_host_srv_rerror_rate": float(
                flow.dst_host_srv_rerror_rate
            ),
            "actual_label": flow.actual_label,
            "actual_family": flow.actual_family,
            "difficulty_level": flow.difficulty_level,
        },
    }


def _commit_status_change(db) -> None:
    """Small transaction boundary kept separate for focused rollback testing."""
    db.commit()


def update_network_incident_status(
    db, incident_id: int, status: str
) -> dict[str, Any] | None:
    """Update only the supported workflow status and return persisted detail."""
    normalized_status = _validate_optional_filter(
        status, ALLOWED_INCIDENT_STATUSES, "status"
    )
    incident = db.get(NetworkIncident, incident_id)
    if incident is None:
        return None
    try:
        incident.status = normalized_status
        _commit_status_change(db)
        db.refresh(incident)
    except Exception as error:
        db.rollback()
        LOGGER.exception("Network incident status update failed")
        raise NetworkIncidentPersistenceError(
            "Network incident status could not be updated."
        ) from error
    return get_network_incident_detail(db, incident_id)
