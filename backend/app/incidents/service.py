from datetime import datetime

from backend.app.database.models import Incident
from backend.app.detection.rules import run_rule_engine_for_file
from backend.app.incidents.explanations import (
    format_incident_response,
    validate_incident_status,
)


def create_incidents_from_rule_findings(file_id, db):
    findings = run_rule_engine_for_file(file_id, db)

    try:
        db.query(Incident).filter(Incident.file_id == file_id).delete(
            synchronize_session=False
        )

        incidents = []

        for finding in findings:
            incident = Incident(
                file_id=file_id,
                ip_address=finding["ip_address"],
                incident_type=finding["incident_type"],
                severity=finding["severity"],
                risk_score=finding["rule_score"],
                evidence=finding["evidence"],
                recommended_action=finding["recommended_action"],
                status="open",
                analyst_note=None,
            )
            incidents.append(incident)

        db.add_all(incidents)
        db.commit()

        return {
            "file_id": file_id,
            "findings_count": len(findings),
            "incidents_created": len(incidents),
        }
    except Exception:
        db.rollback()
        raise


def get_incidents(db, file_id=None, status=None, severity=None):
    query = db.query(Incident)

    if file_id is not None:
        query = query.filter(Incident.file_id == file_id)

    if status is not None:
        query = query.filter(Incident.status == validate_incident_status(status))

    if severity is not None:
        query = query.filter(Incident.severity == severity)

    incidents = query.order_by(Incident.created_at.desc()).all()

    return [format_incident_response(incident) for incident in incidents]


def get_incident_by_id(incident_id, db):
    incident = db.query(Incident).filter(Incident.id == incident_id).first()

    if incident is None:
        return None

    return format_incident_response(incident)


def update_incident_status(incident_id, status, db):
    normalized_status = validate_incident_status(status)
    incident = db.query(Incident).filter(Incident.id == incident_id).first()

    if incident is None:
        return None

    incident.status = normalized_status
    incident.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(incident)

    return format_incident_response(incident)
