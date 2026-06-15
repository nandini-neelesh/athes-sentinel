from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.app.database.session import get_db
from backend.app.incidents.service import (
    create_incidents_from_rule_findings,
    get_incident_by_id,
    get_incidents,
    update_incident_status,
)


router = APIRouter(
    prefix="/incidents",
    tags=["Incidents"],
)


class IncidentStatusUpdate(BaseModel):
    status: str


@router.post("/generate/{file_id}")
def generate_incidents(file_id: int, db=Depends(get_db)):
    try:
        return create_incidents_from_rule_findings(file_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
def list_incidents(
    file_id: int | None = None,
    status: str | None = None,
    severity: str | None = None,
    db=Depends(get_db),
):
    try:
        return get_incidents(db, file_id=file_id, status=status, severity=severity)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{incident_id}")
def read_incident(incident_id: int, db=Depends(get_db)):
    incident = get_incident_by_id(incident_id, db)

    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")

    return incident


@router.patch("/{incident_id}/status")
def patch_incident_status(
    incident_id: int,
    body: IncidentStatusUpdate,
    db=Depends(get_db),
):
    try:
        incident = update_incident_status(incident_id, body.status, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")

    return incident
