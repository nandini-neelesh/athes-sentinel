import math

import pandas as pd

from backend.app.database.models import IPFeature, RawLog


SENSITIVE_ENDPOINTS = [
    "/admin",
    "/config",
    "/.env",
    "/api/users",
    "/settings",
]


def raw_logs_to_dataframe(raw_logs):
    rows = []

    for raw_log in raw_logs:
        rows.append(
            {
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
        )

    return pd.DataFrame(rows)


def calculate_endpoint_entropy(endpoints):
    endpoint_series = pd.Series(endpoints).dropna()

    if len(endpoint_series) == 0 or endpoint_series.nunique() <= 1:
        return 0.0

    endpoint_counts = endpoint_series.value_counts()
    total_endpoints = endpoint_counts.sum()
    entropy = 0.0

    for count in endpoint_counts:
        probability = count / total_endpoints
        entropy -= probability * math.log2(probability)

    return float(entropy)


def _is_sensitive_endpoint(endpoint):
    if pd.isna(endpoint):
        return False

    endpoint_text = str(endpoint)

    for sensitive_endpoint in SENSITIVE_ENDPOINTS:
        if endpoint_text == sensitive_endpoint or endpoint_text.startswith(
            sensitive_endpoint + "/"
        ):
            return True

    return False


def compute_ip_feature_dataframe(df):
    feature_rows = []

    cleaned_df = df.copy()
    cleaned_df["timestamp"] = pd.to_datetime(cleaned_df["timestamp"])
    cleaned_df["status_code"] = pd.to_numeric(cleaned_df["status_code"])
    cleaned_df["response_time_ms"] = pd.to_numeric(cleaned_df["response_time_ms"])

    for ip_address, ip_logs in cleaned_df.groupby("ip_address"):
        total_requests = len(ip_logs)

        endpoint_series = ip_logs["endpoint"].fillna("")
        event_type_series = ip_logs["event_type"].fillna("")
        status_code_series = ip_logs["status_code"]

        failed_login_mask = (
            (endpoint_series == "/login") & (status_code_series.isin([401, 403]))
        ) | event_type_series.str.contains("login_failed", case=False, na=False)

        success_login_mask = (
            (endpoint_series == "/login") & (status_code_series == 200)
        ) | event_type_series.str.contains("login_success", case=False, na=False)

        error_4xx_count = int(
            ((status_code_series >= 400) & (status_code_series <= 499)).sum()
        )
        error_5xx_count = int(
            ((status_code_series >= 500) & (status_code_series <= 599)).sum()
        )

        first_timestamp = ip_logs["timestamp"].min()
        last_timestamp = ip_logs["timestamp"].max()
        active_duration_minutes = (
            last_timestamp - first_timestamp
        ).total_seconds() / 60

        if active_duration_minutes == 0:
            active_duration_minutes = 1

        feature_rows.append(
            {
                "ip_address": ip_address,
                "total_requests": int(total_requests),
                "failed_login_count": int(failed_login_mask.sum()),
                "success_login_count": int(success_login_mask.sum()),
                "error_4xx_count": error_4xx_count,
                "error_5xx_count": error_5xx_count,
                "error_rate": float(
                    (error_4xx_count + error_5xx_count) / total_requests
                ),
                "unique_endpoints": int(endpoint_series.nunique()),
                "endpoint_entropy": calculate_endpoint_entropy(endpoint_series),
                "avg_response_time": float(ip_logs["response_time_ms"].mean()),
                "max_response_time": float(ip_logs["response_time_ms"].max()),
                "sensitive_endpoint_count": int(
                    endpoint_series.apply(_is_sensitive_endpoint).sum()
                ),
                "request_frequency": float(total_requests / active_duration_minutes),
            }
        )

    return pd.DataFrame(feature_rows)


def generate_ip_features_for_file(file_id, db):
    raw_logs = db.query(RawLog).filter(RawLog.file_id == file_id).all()

    if not raw_logs:
        raise ValueError(f"No raw logs found for file_id={file_id}.")

    raw_log_df = raw_logs_to_dataframe(raw_logs)
    feature_df = compute_ip_feature_dataframe(raw_log_df)

    try:
        db.query(IPFeature).filter(IPFeature.file_id == file_id).delete(
            synchronize_session=False
        )

        ip_features = []

        for row in feature_df.to_dict(orient="records"):
            ip_feature = IPFeature(
                file_id=file_id,
                ip_address=row["ip_address"],
                total_requests=row["total_requests"],
                failed_login_count=row["failed_login_count"],
                success_login_count=row["success_login_count"],
                error_4xx_count=row["error_4xx_count"],
                error_5xx_count=row["error_5xx_count"],
                error_rate=row["error_rate"],
                unique_endpoints=row["unique_endpoints"],
                endpoint_entropy=row["endpoint_entropy"],
                avg_response_time=row["avg_response_time"],
                max_response_time=row["max_response_time"],
                sensitive_endpoint_count=row["sensitive_endpoint_count"],
                request_frequency=row["request_frequency"],
                ml_anomaly_score=None,
            )
            ip_features.append(ip_feature)

        db.add_all(ip_features)
        db.commit()

        return {
            "file_id": file_id,
            "ip_count": len(ip_features),
            "features_created": len(ip_features),
        }
    except Exception:
        db.rollback()
        raise


def get_ip_features_for_file(file_id, db):
    ip_features = db.query(IPFeature).filter(IPFeature.file_id == file_id).all()

    return [
        {
            "id": ip_feature.id,
            "file_id": ip_feature.file_id,
            "ip_address": ip_feature.ip_address,
            "total_requests": ip_feature.total_requests,
            "failed_login_count": ip_feature.failed_login_count,
            "success_login_count": ip_feature.success_login_count,
            "error_4xx_count": ip_feature.error_4xx_count,
            "error_5xx_count": ip_feature.error_5xx_count,
            "error_rate": ip_feature.error_rate,
            "unique_endpoints": ip_feature.unique_endpoints,
            "endpoint_entropy": ip_feature.endpoint_entropy,
            "avg_response_time": ip_feature.avg_response_time,
            "max_response_time": ip_feature.max_response_time,
            "sensitive_endpoint_count": ip_feature.sensitive_endpoint_count,
            "request_frequency": ip_feature.request_frequency,
            "ml_anomaly_score": ip_feature.ml_anomaly_score,
        }
        for ip_feature in ip_features
    ]
