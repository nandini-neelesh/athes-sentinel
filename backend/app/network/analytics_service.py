"""SQL-backed dashboard and analytics reads for persisted network results."""

from __future__ import annotations

from typing import Any

from sqlalchemy import case, func

from backend.app.database.network_models import (
    NetworkDataset,
    NetworkFlow,
    NetworkIncident,
    NetworkPrediction,
)
from backend.app.network.analysis_service import persisted_analysis_summary
from backend.app.network.incident_service import compact_incident_row

PROBABILITY_BUCKETS = [
    (0.00, 0.10, "0.00–0.10"),
    (0.10, 0.20, "0.10–0.20"),
    (0.20, 0.30, "0.20–0.30"),
    (0.30, 0.38, "0.30–0.38"),
    (0.38, 0.50, "0.38–0.50"),
    (0.50, 0.60, "0.50–0.60"),
    (0.60, 0.75, "0.60–0.75"),
    (0.75, 0.90, "0.75–0.90"),
    (0.90, 1.00, "0.90–1.00"),
]
FAMILY_ORDER = ["normal", "dos", "probe", "r2l", "u2r"]


def _percentage(part: int, whole: int) -> float:
    """Return a human-facing 0-100 percentage with zero-safe division."""
    return float(part / whole * 100) if whole else 0.0


def get_network_dashboard(
    db, dataset_id: int
) -> dict[str, Any] | None:
    """Return persisted dataset, model, prediction, and incident dashboard data."""
    dataset = db.get(NetworkDataset, dataset_id)
    if dataset is None:
        return None
    summary = persisted_analysis_summary(db, dataset_id)

    incident_stats = (
        db.query(
            func.count(NetworkIncident.id),
            func.coalesce(
                func.sum(case((NetworkIncident.status == "open", 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (NetworkIncident.status == "investigating", 1),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case((NetworkIncident.status == "resolved", 1), else_=0)
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (NetworkIncident.status == "false_positive", 1),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case((NetworkIncident.severity == "critical", 1), else_=0)
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case((NetworkIncident.severity == "high", 1), else_=0)
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case((NetworkIncident.severity == "medium", 1), else_=0)
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case((NetworkIncident.severity == "low", 1), else_=0)
                ),
                0,
            ),
            func.max(NetworkIncident.risk_score),
        )
        .filter(NetworkIncident.dataset_id == dataset_id)
        .one()
    )
    priority_rows = (
        db.query(NetworkIncident, NetworkPrediction, NetworkFlow)
        .join(
            NetworkPrediction,
            NetworkPrediction.id == NetworkIncident.prediction_id,
        )
        .join(NetworkFlow, NetworkFlow.id == NetworkIncident.flow_id)
        .filter(NetworkIncident.dataset_id == dataset_id)
        .order_by(
            NetworkIncident.risk_score.desc(),
            NetworkIncident.created_at.asc(),
            NetworkIncident.id.asc(),
        )
        .limit(5)
        .all()
    )
    model = None
    if (
        dataset.model_name is not None
        and summary["model_version"] is not None
        and dataset.model_threshold is not None
    ):
        model = {
            "model_name": dataset.model_name,
            "model_version": summary["model_version"],
            "threshold_probability": float(dataset.model_threshold),
        }

    return {
        "dataset": {
            "dataset_id": dataset.id,
            "filename": dataset.filename,
            "uploaded_at": dataset.uploaded_at,
            "total_flows": summary["total_flows"],
            "has_ground_truth": dataset.has_ground_truth,
            "source_type": dataset.source_type,
            "analysis_status": dataset.analysis_status,
            "analysis_error": dataset.analysis_error,
            "analysis_started_at": dataset.analysis_started_at,
            "analysis_completed_at": dataset.analysis_completed_at,
        },
        "model": model,
        "prediction_kpis": {
            "total_predictions": summary["total_predictions"],
            "predicted_normal": summary["predicted_normal"],
            "predicted_attack": summary["predicted_attack"],
            "predicted_attack_percentage": summary[
                "predicted_attack_percentage"
            ],
            "minimum_attack_probability": summary["minimum_probability"],
            "maximum_attack_probability": summary["maximum_probability"],
            "mean_attack_probability": summary["mean_probability"],
        },
        "incident_kpis": {
            "total_incidents": int(incident_stats[0] or 0),
            "open_incidents": int(incident_stats[1] or 0),
            "investigating_incidents": int(incident_stats[2] or 0),
            "resolved_incidents": int(incident_stats[3] or 0),
            "false_positive_status_incidents": int(incident_stats[4] or 0),
            "critical_incidents": int(incident_stats[5] or 0),
            "high_incidents": int(incident_stats[6] or 0),
            "medium_incidents": int(incident_stats[7] or 0),
            "low_incidents": int(incident_stats[8] or 0),
            "highest_risk_score": (
                float(incident_stats[9])
                if incident_stats[9] is not None
                else None
            ),
        },
        "benchmark_metrics": summary["benchmark_metrics"],
        "priority_incidents": [
            compact_incident_row(incident, prediction, flow)
            for incident, prediction, flow in priority_rows
        ],
    }


def _grouped_prediction_distribution(
    db,
    dataset_id: int,
    group_column,
    result_name: str,
    include_maximum: bool = False,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Aggregate prediction outcomes by one original categorical flow field."""
    total_expression = func.count(NetworkPrediction.id)
    attack_expression = func.coalesce(
        func.sum(
            case((NetworkPrediction.predicted_binary == 1, 1), else_=0)
        ),
        0,
    )
    selected = [
        group_column,
        total_expression.label("total_records"),
        attack_expression.label("predicted_attacks"),
        func.avg(NetworkPrediction.rf_attack_probability).label(
            "mean_probability"
        ),
    ]
    if include_maximum:
        selected.append(
            func.max(NetworkPrediction.rf_attack_probability).label(
                "maximum_probability"
            )
        )
    query = (
        db.query(*selected)
        .join(
            NetworkPrediction,
            NetworkPrediction.flow_id == NetworkFlow.id,
        )
        .filter(NetworkPrediction.dataset_id == dataset_id)
        .group_by(group_column)
        .order_by(total_expression.desc(), group_column.asc())
    )
    if limit is not None:
        query = query.limit(limit)

    results = []
    for row in query.all():
        total_records = int(row[1])
        predicted_attacks = int(row[2] or 0)
        result = {
            result_name: str(row[0]),
            "total_records": total_records,
            "predicted_attacks": predicted_attacks,
            "attack_percentage": _percentage(
                predicted_attacks, total_records
            ),
            "mean_attack_probability": float(row[3] or 0),
        }
        if include_maximum:
            result["maximum_attack_probability"] = float(row[4] or 0)
        results.append(result)
    return results


def _probability_histogram(
    db, dataset_id: int, total_predictions: int
) -> list[dict[str, Any]]:
    """Place each constrained 0-1 probability in one left-closed bucket.

    Every bucket is ``[lower, upper)`` except the final bucket, which includes
    probability 1.0.
    """
    if total_predictions == 0:
        return []
    probability = NetworkPrediction.rf_attack_probability
    bucket_expression = case(
        (probability < 0.10, 0),
        (probability < 0.20, 1),
        (probability < 0.30, 2),
        (probability < 0.38, 3),
        (probability < 0.50, 4),
        (probability < 0.60, 5),
        (probability < 0.75, 6),
        (probability < 0.90, 7),
        else_=8,
    )
    rows = (
        db.query(
            bucket_expression.label("bucket_index"),
            func.count(NetworkPrediction.id),
        )
        .filter(NetworkPrediction.dataset_id == dataset_id)
        .group_by(bucket_expression)
        .all()
    )
    counts = {int(index): int(count) for index, count in rows}
    return [
        {
            "lower_bound_probability": lower,
            "upper_bound_probability": upper,
            "label": label,
            "record_count": counts.get(index, 0),
            "percentage": _percentage(
                counts.get(index, 0), total_predictions
            ),
        }
        for index, (lower, upper, label) in enumerate(PROBABILITY_BUCKETS)
    ]


def _benchmark_distributions(
    db,
    dataset_id: int,
    total_predictions: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    family_rows = (
        db.query(NetworkFlow.actual_family, func.count(NetworkPrediction.id))
        .join(
            NetworkPrediction,
            NetworkPrediction.flow_id == NetworkFlow.id,
        )
        .filter(NetworkPrediction.dataset_id == dataset_id)
        .group_by(NetworkFlow.actual_family)
        .all()
    )
    family_counts = {
        str(family): int(count)
        for family, count in family_rows
        if family is not None
    }
    correctness_rows = (
        db.query(
            NetworkPrediction.is_correct,
            func.count(NetworkPrediction.id),
        )
        .filter(NetworkPrediction.dataset_id == dataset_id)
        .group_by(NetworkPrediction.is_correct)
        .all()
    )
    correctness_counts = {
        bool(value): int(count)
        for value, count in correctness_rows
        if value is not None
    }
    return (
        [
            {"value": family, "record_count": family_counts.get(family, 0)}
            for family in FAMILY_ORDER
        ],
        [
            {"value": "correct", "record_count": correctness_counts.get(True, 0)},
            {
                "value": "incorrect",
                "record_count": correctness_counts.get(False, 0),
            },
        ],
    )


def get_network_analytics(
    db, dataset_id: int, service_limit: int
) -> dict[str, Any] | None:
    """Return persisted prediction and benchmark distributions using SQL."""
    dataset = db.get(NetworkDataset, dataset_id)
    if dataset is None:
        return None
    summary = persisted_analysis_summary(db, dataset_id)
    total_predictions = summary["total_predictions"]
    if total_predictions == 0:
        return {
            "dataset_id": dataset_id,
            "analysis_status": dataset.analysis_status,
            "prediction_distribution": [],
            "protocol_distribution": [],
            "service_distribution": [],
            "flag_distribution": [],
            "severity_distribution": {
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
            },
            "probability_histogram": [],
            "actual_family_distribution": None,
            "correctness_distribution": None,
            "benchmark_metrics": None,
        }

    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for severity, count in (
        db.query(NetworkIncident.severity, func.count(NetworkIncident.id))
        .filter(NetworkIncident.dataset_id == dataset_id)
        .group_by(NetworkIncident.severity)
        .all()
    ):
        if severity in severity_counts:
            severity_counts[severity] = int(count)

    actual_family_distribution = None
    correctness_distribution = None
    if dataset.has_ground_truth:
        actual_family_distribution, correctness_distribution = (
            _benchmark_distributions(db, dataset_id, total_predictions)
        )

    return {
        "dataset_id": dataset_id,
        "analysis_status": dataset.analysis_status,
        "prediction_distribution": [
            {
                "predicted_class": "normal",
                "record_count": summary["predicted_normal"],
                "percentage": _percentage(
                    summary["predicted_normal"], total_predictions
                ),
            },
            {
                "predicted_class": "attack",
                "record_count": summary["predicted_attack"],
                "percentage": _percentage(
                    summary["predicted_attack"], total_predictions
                ),
            },
        ],
        "protocol_distribution": _grouped_prediction_distribution(
            db,
            dataset_id,
            NetworkFlow.protocol_type,
            "protocol",
        ),
        "service_distribution": _grouped_prediction_distribution(
            db,
            dataset_id,
            NetworkFlow.service,
            "service",
            include_maximum=True,
            limit=service_limit,
        ),
        "flag_distribution": _grouped_prediction_distribution(
            db,
            dataset_id,
            NetworkFlow.flag,
            "flag",
        ),
        "severity_distribution": severity_counts,
        "probability_histogram": _probability_histogram(
            db, dataset_id, total_predictions
        ),
        "actual_family_distribution": actual_family_distribution,
        "correctness_distribution": correctness_distribution,
        "benchmark_metrics": summary["benchmark_metrics"],
    }
