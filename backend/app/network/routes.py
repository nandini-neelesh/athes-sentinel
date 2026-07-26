"""Authenticated upload and read routes for network-flow datasets."""

import logging

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from backend.app.auth.service import get_current_user
from backend.app.database.session import get_db
from backend.app.network.analytics_service import (
    get_network_analytics,
    get_network_dashboard,
)
from backend.app.network.analysis_service import (
    NetworkAnalysisConflictError,
    NetworkAnalysisExecutionError,
    NetworkAnalysisNoFlowsError,
    NetworkAnalysisNotFoundError,
    analyze_network_dataset,
    persisted_analysis_summary,
)
from backend.app.network.incident_service import (
    NetworkIncidentPersistenceError,
    get_network_incident_detail,
    list_network_incidents,
    update_network_incident_status,
)
from backend.app.network.schemas import (
    NetworkAnalyticsResponse,
    NetworkAnalysisResponse,
    NetworkDashboardResponse,
    NetworkDatasetDetail,
    NetworkDatasetUploadResponse,
    NetworkIncidentDetail,
    NetworkIncidentStatusUpdate,
    PaginatedNetworkDatasets,
    PaginatedNetworkFlows,
    PaginatedNetworkIncidents,
)
from backend.app.network.service import (
    MAX_UPLOAD_BYTES,
    NetworkPersistenceError,
    NetworkUploadTooLargeError,
    NetworkValidationError,
    get_network_dataset_detail,
    ingest_network_dataset,
    list_network_datasets,
    list_network_flows,
)

LOGGER = logging.getLogger(__name__)
router = APIRouter(prefix="/network", tags=["Network"])


@router.post(
    "/datasets/upload",
    response_model=NetworkDatasetUploadResponse,
    status_code=201,
)
async def upload_network_dataset(
    file: UploadFile = File(...),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Read at most 50 MB and persist one fully validated network dataset."""
    del current_user
    try:
        file_bytes = await file.read(MAX_UPLOAD_BYTES + 1)
        return ingest_network_dataset(db, file.filename, file_bytes)
    except NetworkUploadTooLargeError as error:
        raise HTTPException(status_code=413, detail=str(error)) from error
    except NetworkValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except NetworkPersistenceError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    except Exception as error:
        db.rollback()
        LOGGER.exception("Unexpected network upload failure")
        raise HTTPException(
            status_code=500,
            detail="Network dataset upload failed unexpectedly.",
        ) from error
    finally:
        await file.close()


@router.get("/datasets", response_model=PaginatedNetworkDatasets)
def read_network_datasets(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List uploaded network datasets newest first."""
    del current_user
    return list_network_datasets(db, limit=limit, offset=offset)


@router.post(
    "/datasets/{dataset_id}/analyze",
    response_model=NetworkAnalysisResponse,
)
def analyze_stored_network_dataset(
    dataset_id: int,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Run the frozen binary detector or reuse a consistent completed result."""
    del current_user
    try:
        return analyze_network_dataset(db, dataset_id)
    except NetworkAnalysisNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except NetworkAnalysisNoFlowsError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except NetworkAnalysisConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except NetworkAnalysisExecutionError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.get(
    "/datasets/{dataset_id}/analysis",
    response_model=NetworkAnalysisResponse,
)
def read_stored_network_analysis(
    dataset_id: int,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return persisted status and results without running inference."""
    del current_user
    summary = persisted_analysis_summary(db, dataset_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Network dataset not found")
    return summary


@router.get(
    "/datasets/{dataset_id}/dashboard",
    response_model=NetworkDashboardResponse,
)
def read_network_dashboard(
    dataset_id: int,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return persisted KPIs and priority incidents without inference."""
    del current_user
    dashboard = get_network_dashboard(db, dataset_id)
    if dashboard is None:
        raise HTTPException(status_code=404, detail="Network dataset not found")
    return dashboard


@router.get(
    "/datasets/{dataset_id}/analytics",
    response_model=NetworkAnalyticsResponse,
)
def read_network_analytics(
    dataset_id: int,
    service_limit: int = Query(default=10, ge=1, le=50),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return SQL-derived distributions from persisted prediction results."""
    del current_user
    analytics = get_network_analytics(
        db, dataset_id, service_limit=service_limit
    )
    if analytics is None:
        raise HTTPException(status_code=404, detail="Network dataset not found")
    return analytics


@router.get(
    "/datasets/{dataset_id}/incidents",
    response_model=PaginatedNetworkIncidents,
)
def read_network_incident_queue(
    dataset_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: str | None = None,
    severity: str | None = None,
    search: str | None = None,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return one filtered, risk-ordered page of persisted incidents."""
    del current_user
    try:
        page = list_network_incidents(
            db,
            dataset_id,
            limit=limit,
            offset=offset,
            status=status,
            severity=severity,
            search=search,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if page is None:
        raise HTTPException(status_code=404, detail="Network dataset not found")
    return page


@router.get(
    "/incidents/{incident_id}",
    response_model=NetworkIncidentDetail,
)
def read_network_incident(
    incident_id: int,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return one persisted incident with prediction and real flow context."""
    del current_user
    detail = get_network_incident_detail(db, incident_id)
    if detail is None:
        raise HTTPException(
            status_code=404, detail="Network incident not found"
        )
    return detail


@router.patch(
    "/incidents/{incident_id}/status",
    response_model=NetworkIncidentDetail,
)
def patch_network_incident_status(
    incident_id: int,
    body: NetworkIncidentStatusUpdate,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Persist only the supported analyst workflow status."""
    del current_user
    try:
        detail = update_network_incident_status(
            db, incident_id, body.status
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except NetworkIncidentPersistenceError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    if detail is None:
        raise HTTPException(
            status_code=404, detail="Network incident not found"
        )
    return detail


@router.get("/datasets/{dataset_id}", response_model=NetworkDatasetDetail)
def read_network_dataset(
    dataset_id: int,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return one dataset and its current flow/prediction/incident counts."""
    del current_user
    detail = get_network_dataset_detail(db, dataset_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Network dataset not found")
    return detail


@router.get(
    "/datasets/{dataset_id}/flows",
    response_model=PaginatedNetworkFlows,
)
def read_network_dataset_flows(
    dataset_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return source-ordered original flows without encoded model features."""
    del current_user
    page = list_network_flows(
        db,
        dataset_id=dataset_id,
        limit=limit,
        offset=offset,
    )
    if page is None:
        raise HTTPException(status_code=404, detail="Network dataset not found")
    return page
