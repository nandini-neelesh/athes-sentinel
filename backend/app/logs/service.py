import pandas as pd

from backend.app.database.models import LogFile, RawLog
from backend.app.logs.validator import validate_log_dataframe


def _clean_optional_value(value):
    if pd.isna(value):
        return None

    return value


def save_uploaded_logs(file, db):
    try:
        dataframe = pd.read_csv(file.file)
        cleaned_dataframe = validate_log_dataframe(dataframe)

        log_file = LogFile(filename=file.filename)
        db.add(log_file)
        db.flush()

        raw_logs = []

        for row in cleaned_dataframe.to_dict(orient="records"):
            raw_log = RawLog(
                file_id=log_file.id,
                timestamp=row["timestamp"],
                ip_address=row["ip_address"],
                user_id=_clean_optional_value(row["user_id"]),
                endpoint=row["endpoint"],
                method=row["method"],
                status_code=row["status_code"],
                response_time_ms=row["response_time_ms"],
                event_type=_clean_optional_value(row["event_type"]),
                user_agent=_clean_optional_value(row["user_agent"]),
            )
            raw_logs.append(raw_log)

        db.add_all(raw_logs)
        db.commit()
        db.refresh(log_file)

        return {
            "filename": log_file.filename,
            "file_id": log_file.id,
            "rows_inserted": len(raw_logs),
        }
    except Exception:
        db.rollback()
        raise


def get_log_files(db):
    log_files = db.query(LogFile).order_by(LogFile.uploaded_at.desc()).all()

    return [
        {
            "id": log_file.id,
            "filename": log_file.filename,
            "uploaded_at": log_file.uploaded_at,
            "uploaded_by": log_file.uploaded_by,
        }
        for log_file in log_files
    ]


def get_raw_logs(db, file_id=None, limit=100):
    query = db.query(RawLog)

    if file_id is not None:
        query = query.filter(RawLog.file_id == file_id)

    raw_logs = query.order_by(RawLog.id.desc()).limit(limit).all()

    return [
        {
            "id": raw_log.id,
            "file_id": raw_log.file_id,
            "timestamp": raw_log.timestamp,
            "ip_address": raw_log.ip_address,
            "user_id": raw_log.user_id,
            "endpoint": raw_log.endpoint,
            "method": raw_log.method,
            "status_code": raw_log.status_code,
            "response_time_ms": raw_log.response_time_ms,
            "event_type": raw_log.event_type,
            "user_agent": raw_log.user_agent,
        }
        for raw_log in raw_logs
    ]
