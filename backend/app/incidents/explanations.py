from datetime import datetime


ALLOWED_STATUSES = {
    "open",
    "investigating",
    "resolved",
    "false_positive",
}


def normalize_status(status):
    return status.strip().lower()


def validate_incident_status(status):
    normalized_status = normalize_status(status)

    if normalized_status not in ALLOWED_STATUSES:
        allowed_text = ", ".join(sorted(ALLOWED_STATUSES))
        raise ValueError(f"Invalid incident status. Allowed statuses: {allowed_text}")

    return normalized_status


def _format_datetime(value):
    if isinstance(value, datetime):
        return value.isoformat()

    return value


def format_incident_response(incident):
    return {
        "id": incident.id,
        "file_id": incident.file_id,
        "ip_address": incident.ip_address,
        "incident_type": incident.incident_type,
        "severity": incident.severity,
        "risk_score": incident.risk_score,
        "evidence": incident.evidence,
        "recommended_action": incident.recommended_action,
        "status": incident.status,
        "analyst_note": incident.analyst_note,
        "created_at": _format_datetime(incident.created_at),
        "updated_at": _format_datetime(incident.updated_at),
    }
