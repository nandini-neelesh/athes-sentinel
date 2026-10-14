from fastapi import APIRouter, Depends, HTTPException

from backend.app.auth.service import get_current_user

from backend.app.database.session import get_db
from backend.app.features.ip_features import (
    generate_ip_features_for_file,
    get_ip_features_for_file,
)


router = APIRouter(
    prefix="/features",
    tags=["Features"],
    dependencies=[Depends(get_current_user)],
)


@router.post("/generate/{file_id}")
def generate_features(file_id: int, db=Depends(get_db)):
    try:
        return generate_ip_features_for_file(file_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{file_id}")
def list_features(file_id: int, db=Depends(get_db)):
    return get_ip_features_for_file(file_id, db)
