from fastapi import APIRouter, Depends, HTTPException

from backend.app.database.session import get_db
from backend.app.detection.ml_model import (
    get_ml_scores_for_file,
    run_isolation_forest_for_file,
)


router = APIRouter(
    prefix="/ml",
    tags=["ML Anomaly Detection"],
)


@router.post("/run/{file_id}")
def run_ml_detection(file_id: int, db=Depends(get_db)):
    try:
        return run_isolation_forest_for_file(file_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/scores/{file_id}")
def list_ml_scores(file_id: int, db=Depends(get_db)):
    return get_ml_scores_for_file(file_id, db)
