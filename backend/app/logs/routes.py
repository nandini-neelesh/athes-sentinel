from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from backend.app.auth.service import get_current_user
from backend.app.database.session import get_db
from backend.app.logs.service import get_log_files, get_raw_logs, save_uploaded_logs


router = APIRouter(
    prefix="/logs",
    tags=["Logs"],
    dependencies=[Depends(get_current_user)],
)


@router.post("/upload")
def upload_logs(
    file: UploadFile = File(...),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        return save_uploaded_logs(file, db, uploaded_by=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/files")
def list_log_files(db=Depends(get_db)):
    return get_log_files(db)


@router.get("")
def list_raw_logs(file_id: int | None = None, limit: int = 100, db=Depends(get_db)):
    return get_raw_logs(db, file_id=file_id, limit=limit)
