from fastapi import APIRouter, Depends, Query

from backend.app.analytics.service import (
    get_error_rate_by_endpoint,
    get_hourly_traffic,
    get_slowest_endpoints,
    get_status_code_distribution,
    get_summary,
    get_top_endpoints,
    get_top_ips,
)
from backend.app.database.session import get_db


router = APIRouter(
    prefix="/analytics",
    tags=["Analytics"],
)


@router.get("/summary/{file_id}")
def read_summary(file_id: int, db=Depends(get_db)):
    return get_summary(file_id, db)


@router.get("/status-codes/{file_id}")
def read_status_code_distribution(file_id: int, db=Depends(get_db)):
    return get_status_code_distribution(file_id, db)


@router.get("/top-ips/{file_id}")
def read_top_ips(
    file_id: int,
    limit: int = Query(10, ge=1, le=50),
    db=Depends(get_db),
):
    return get_top_ips(file_id, db, limit)


@router.get("/hourly-traffic/{file_id}")
def read_hourly_traffic(file_id: int, db=Depends(get_db)):
    return get_hourly_traffic(file_id, db)


@router.get("/top-endpoints/{file_id}")
def read_top_endpoints(
    file_id: int,
    limit: int = Query(10, ge=1, le=50),
    db=Depends(get_db),
):
    return get_top_endpoints(file_id, db, limit)


@router.get("/slowest-endpoints/{file_id}")
def read_slowest_endpoints(
    file_id: int,
    limit: int = Query(10, ge=1, le=50),
    db=Depends(get_db),
):
    return get_slowest_endpoints(file_id, db, limit)


@router.get("/error-rate-by-endpoint/{file_id}")
def read_error_rate_by_endpoint(
    file_id: int,
    limit: int = Query(10, ge=1, le=50),
    db=Depends(get_db),
):
    return get_error_rate_by_endpoint(file_id, db, limit)
