from collections import defaultdict

from sqlalchemy import func

from backend.app.database.models import IPFeature, Incident, RawLog


def get_summary(file_id, db):
    total_logs = db.query(RawLog).filter(RawLog.file_id == file_id).count()
    unique_ips = (
        db.query(RawLog.ip_address)
        .filter(RawLog.file_id == file_id)
        .distinct()
        .count()
    )
    total_incidents = db.query(Incident).filter(Incident.file_id == file_id).count()
    open_incidents = (
        db.query(Incident)
        .filter(Incident.file_id == file_id, Incident.status == "open")
        .count()
    )
    critical_incidents = (
        db.query(Incident)
        .filter(Incident.file_id == file_id, Incident.severity == "critical")
        .count()
    )
    high_incidents = (
        db.query(Incident)
        .filter(Incident.file_id == file_id, Incident.severity == "high")
        .count()
    )
    max_risk_score = (
        db.query(func.max(Incident.risk_score))
        .filter(Incident.file_id == file_id)
        .scalar()
    )
    avg_ml_anomaly_score = (
        db.query(func.avg(IPFeature.ml_anomaly_score))
        .filter(
            IPFeature.file_id == file_id,
            IPFeature.ml_anomaly_score.isnot(None),
        )
        .scalar()
    )

    return {
        "file_id": file_id,
        "total_logs": total_logs,
        "unique_ips": unique_ips,
        "total_incidents": total_incidents,
        "open_incidents": open_incidents,
        "critical_incidents": critical_incidents,
        "high_incidents": high_incidents,
        "max_risk_score": round(float(max_risk_score or 0), 2),
        "avg_ml_anomaly_score": round(float(avg_ml_anomaly_score or 0), 2),
    }


def get_status_code_distribution(file_id, db):
    rows = (
        db.query(RawLog.status_code, func.count(RawLog.id))
        .filter(RawLog.file_id == file_id)
        .group_by(RawLog.status_code)
        .order_by(RawLog.status_code.asc())
        .all()
    )

    return [
        {
            "status_code": status_code,
            "count": count,
        }
        for status_code, count in rows
    ]


def get_top_ips(file_id, db, limit=10):
    rows = (
        db.query(RawLog.ip_address, func.count(RawLog.id).label("request_count"))
        .filter(RawLog.file_id == file_id)
        .group_by(RawLog.ip_address)
        .order_by(func.count(RawLog.id).desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "ip_address": ip_address,
            "request_count": request_count,
        }
        for ip_address, request_count in rows
    ]


def get_hourly_traffic(file_id, db):
    raw_logs = (
        db.query(RawLog.timestamp)
        .filter(RawLog.file_id == file_id)
        .order_by(RawLog.timestamp.asc())
        .all()
    )
    hourly_counts = defaultdict(int)

    for (timestamp,) in raw_logs:
        hour = timestamp.replace(minute=0, second=0, microsecond=0)
        hour_text = hour.strftime("%Y-%m-%d %H:%M")
        hourly_counts[hour_text] += 1

    return [
        {
            "hour": hour,
            "request_count": hourly_counts[hour],
        }
        for hour in sorted(hourly_counts)
    ]


def get_top_endpoints(file_id, db, limit=10):
    rows = (
        db.query(RawLog.endpoint, func.count(RawLog.id).label("request_count"))
        .filter(RawLog.file_id == file_id)
        .group_by(RawLog.endpoint)
        .order_by(func.count(RawLog.id).desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "endpoint": endpoint,
            "request_count": request_count,
        }
        for endpoint, request_count in rows
    ]


def get_slowest_endpoints(file_id, db, limit=10):
    rows = (
        db.query(
            RawLog.endpoint,
            func.avg(RawLog.response_time_ms).label("avg_response_time_ms"),
            func.max(RawLog.response_time_ms).label("max_response_time_ms"),
        )
        .filter(RawLog.file_id == file_id)
        .group_by(RawLog.endpoint)
        .order_by(func.avg(RawLog.response_time_ms).desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "endpoint": endpoint,
            "avg_response_time_ms": round(float(avg_response_time_ms or 0), 2),
            "max_response_time_ms": round(float(max_response_time_ms or 0), 2),
        }
        for endpoint, avg_response_time_ms, max_response_time_ms in rows
    ]


def get_error_rate_by_endpoint(file_id, db, limit=10):
    raw_logs = db.query(RawLog).filter(RawLog.file_id == file_id).all()
    endpoint_counts = {}

    for raw_log in raw_logs:
        if raw_log.endpoint not in endpoint_counts:
            endpoint_counts[raw_log.endpoint] = {
                "endpoint": raw_log.endpoint,
                "total_count": 0,
                "error_count": 0,
            }

        endpoint_counts[raw_log.endpoint]["total_count"] += 1

        if raw_log.status_code >= 400:
            endpoint_counts[raw_log.endpoint]["error_count"] += 1

    results = []

    for endpoint_data in endpoint_counts.values():
        total_count = endpoint_data["total_count"]
        error_count = endpoint_data["error_count"]
        error_rate = 0

        if total_count > 0:
            error_rate = error_count / total_count

        results.append(
            {
                "endpoint": endpoint_data["endpoint"],
                "total_count": total_count,
                "error_count": error_count,
                "error_rate": round(error_rate, 4),
            }
        )

    results.sort(
        key=lambda row: (row["error_rate"], row["total_count"]),
        reverse=True,
    )

    return results[:limit]
