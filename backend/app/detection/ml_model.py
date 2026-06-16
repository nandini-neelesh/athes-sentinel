import pandas as pd
from sklearn.ensemble import IsolationForest

from backend.app.database.models import IPFeature


ML_FEATURE_COLUMNS = [
    "total_requests",
    "failed_login_count",
    "success_login_count",
    "error_4xx_count",
    "error_5xx_count",
    "error_rate",
    "unique_endpoints",
    "endpoint_entropy",
    "avg_response_time",
    "max_response_time",
    "sensitive_endpoint_count",
    "request_frequency",
]


def ip_features_to_dataframe(ip_features):
    rows = []

    for ip_feature in ip_features:
        row = {
            "id": ip_feature.id,
            "file_id": ip_feature.file_id,
            "ip_address": ip_feature.ip_address,
        }

        for column in ML_FEATURE_COLUMNS:
            row[column] = getattr(ip_feature, column)

        rows.append(row)

    feature_df = pd.DataFrame(rows)

    if not feature_df.empty:
        feature_df[ML_FEATURE_COLUMNS] = feature_df[ML_FEATURE_COLUMNS].fillna(0)

    return feature_df


def calculate_ml_risk_scores(feature_df):
    scored_df = feature_df.copy()

    if len(scored_df) < 2:
        scored_df["isolation_forest_label"] = 1
        scored_df["isolation_forest_decision_score"] = 0.0
        scored_df["ml_anomaly_score"] = 0.0
        return scored_df

    model = IsolationForest(
        contamination="auto",
        random_state=42,
    )
    feature_values = scored_df[ML_FEATURE_COLUMNS]

    scored_df["isolation_forest_label"] = model.fit_predict(feature_values)
    scored_df["isolation_forest_decision_score"] = model.decision_function(
        feature_values
    )

    # Lower decision scores are more anomalous, so invert before min-max scaling.
    inverted_scores = -scored_df["isolation_forest_decision_score"]
    minimum_score = inverted_scores.min()
    maximum_score = inverted_scores.max()

    if minimum_score == maximum_score:
        scored_df["ml_anomaly_score"] = 0.0
    else:
        scored_df["ml_anomaly_score"] = (
            (inverted_scores - minimum_score) / (maximum_score - minimum_score) * 100
        ).round(2)

    return scored_df


def run_isolation_forest_for_file(file_id, db):
    ip_features = db.query(IPFeature).filter(IPFeature.file_id == file_id).all()

    if not ip_features:
        raise ValueError(f"No IP feature rows found for file_id={file_id}.")

    feature_df = ip_features_to_dataframe(ip_features)
    scored_df = calculate_ml_risk_scores(feature_df)
    scores_by_id = {
        row["id"]: row["ml_anomaly_score"] for row in scored_df.to_dict(orient="records")
    }

    try:
        for ip_feature in ip_features:
            ip_feature.ml_anomaly_score = float(scores_by_id[ip_feature.id])

        db.commit()

        results = []

        for row in scored_df.to_dict(orient="records"):
            results.append(
                {
                    "ip_feature_id": row["id"],
                    "ip_address": row["ip_address"],
                    "isolation_forest_label": int(row["isolation_forest_label"]),
                    "isolation_forest_decision_score": float(
                        row["isolation_forest_decision_score"]
                    ),
                    "ml_anomaly_score": float(row["ml_anomaly_score"]),
                }
            )

        return {
            "file_id": file_id,
            "ip_count": len(ip_features),
            "scores_updated": len(ip_features),
            "results": results,
        }
    except Exception:
        db.rollback()
        raise


def get_ml_scores_for_file(file_id, db):
    ip_features = db.query(IPFeature).filter(IPFeature.file_id == file_id).all()

    return [
        {
            "id": ip_feature.id,
            "file_id": ip_feature.file_id,
            "ip_address": ip_feature.ip_address,
            "ml_anomaly_score": ip_feature.ml_anomaly_score,
            "total_requests": ip_feature.total_requests,
            "error_rate": ip_feature.error_rate,
            "endpoint_entropy": ip_feature.endpoint_entropy,
            "request_frequency": ip_feature.request_frequency,
            "failed_login_count": ip_feature.failed_login_count,
            "sensitive_endpoint_count": ip_feature.sensitive_endpoint_count,
        }
        for ip_feature in ip_features
    ]
