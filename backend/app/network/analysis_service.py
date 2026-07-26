"""Frozen-model analysis, prediction persistence, and incident generation."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd
from sqlalchemy import and_, case, func, insert

from backend.app.database.network_models import (
    NetworkDataset,
    NetworkFlow,
    NetworkIncident,
    NetworkPrediction,
)
from ml_pipeline.nsl_kdd_schema import FEATURE_COLUMNS, LABEL_COLUMN

LOGGER = logging.getLogger(__name__)
ANALYSIS_BATCH_SIZE = 5_000
ATTACK_THRESHOLD = 0.38
INCIDENT_TYPE = "Predicted Network Intrusion"
RECOMMENDED_ACTION = (
    "Inspect related traffic and authentication events, correlate the connection "
    "with firewall or server records, and validate similar protocol/service/flag "
    "activity before blocking or remediation."
)


def load_final_detector():
    """Call the N3 cached loader without loading ML dependencies on upload."""
    from backend.app.ml.nsl_kdd_inference import (
        load_final_detector as cached_loader,
    )

    return cached_loader()


def predict_network_flows(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Delegate preprocessing and prediction exclusively to the N3 module."""
    from backend.app.ml.nsl_kdd_inference import (
        predict_network_flows as frozen_predict,
    )

    return frozen_predict(dataframe)


def summarize_predictions(predictions: pd.DataFrame) -> dict[str, Any]:
    """Delegate benchmark summarization exclusively to the N3 module."""
    from backend.app.ml.nsl_kdd_inference import (
        summarize_predictions as frozen_summarize,
    )

    return frozen_summarize(predictions)


class NetworkAnalysisNotFoundError(LookupError):
    """Raised when the requested dataset does not exist."""


class NetworkAnalysisNoFlowsError(ValueError):
    """Raised when a dataset contains no stored flow records."""


class NetworkAnalysisConflictError(RuntimeError):
    """Raised when status or child records make analysis unsafe."""


class NetworkAnalysisExecutionError(RuntimeError):
    """Raised after a failed run is rolled back and marked failed."""


def severity_for_probability(probability: float) -> str:
    """Map attack probability to fixed analyst-facing triage severity."""
    if probability >= 0.90:
        return "critical"
    if probability >= 0.75:
        return "high"
    if probability >= 0.60:
        return "medium"
    return "low"


def build_incident_evidence(flow: NetworkFlow, probability: float) -> str:
    """Explain the binary signal using only values present in the stored flow."""
    return (
        "The frozen binary detector classified this connection as suspicious "
        f"at {probability * 100:.2f}% attack probability. "
        f"Observed protocol={flow.protocol_type}, service={flow.service}, "
        f"flag={flow.flag}, src_bytes={flow.src_bytes}, "
        f"dst_bytes={flow.dst_bytes}, "
        f"num_failed_logins={flow.num_failed_logins}, "
        f"logged_in={flow.logged_in}, count={flow.count}, "
        f"srv_count={flow.srv_count}, "
        f"serror_rate={flow.serror_rate}, "
        f"rerror_rate={flow.rerror_rate}. "
        "This is a model signal for analyst review, not confirmation that the "
        "connection is malicious."
    )


def _safe_rate(numerator: int, denominator: int) -> float:
    return float(numerator / denominator) if denominator else 0.0


def _benchmark_metrics_from_counts(
    actual_normal: int,
    actual_attack: int,
    true_negatives: int,
    false_positives: int,
    false_negatives: int,
    true_positives: int,
) -> dict[str, Any]:
    total = actual_normal + actual_attack
    precision = _safe_rate(true_positives, true_positives + false_positives)
    recall = _safe_rate(true_positives, true_positives + false_negatives)
    f1 = _safe_rate(2 * precision * recall, precision + recall)
    f2 = _safe_rate(5 * precision * recall, (4 * precision) + recall)
    return {
        "actual_normal": actual_normal,
        "actual_attack": actual_attack,
        "true_negatives": true_negatives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "true_positives": true_positives,
        "accuracy": _safe_rate(true_negatives + true_positives, total),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "f2": f2,
        "false_positive_rate": _safe_rate(false_positives, actual_normal),
        "false_negative_rate": _safe_rate(false_negatives, actual_attack),
    }


def _child_counts(db, dataset_id: int) -> tuple[int, int, int]:
    prediction_count = int(
        db.query(func.count(NetworkPrediction.id))
        .filter(NetworkPrediction.dataset_id == dataset_id)
        .scalar()
        or 0
    )
    predicted_attack_count = int(
        db.query(func.count(NetworkPrediction.id))
        .filter(
            NetworkPrediction.dataset_id == dataset_id,
            NetworkPrediction.predicted_binary == 1,
        )
        .scalar()
        or 0
    )
    incident_count = int(
        db.query(func.count(NetworkIncident.id))
        .filter(NetworkIncident.dataset_id == dataset_id)
        .scalar()
        or 0
    )
    return prediction_count, predicted_attack_count, incident_count


def _completed_state_is_consistent(
    db, dataset_id: int, flow_count: int
) -> bool:
    prediction_count, attack_count, incident_count = _child_counts(
        db, dataset_id
    )
    missing_attack_incidents = int(
        db.query(func.count(NetworkPrediction.id))
        .outerjoin(
            NetworkIncident,
            NetworkIncident.prediction_id == NetworkPrediction.id,
        )
        .filter(
            NetworkPrediction.dataset_id == dataset_id,
            NetworkPrediction.predicted_binary == 1,
            NetworkIncident.id.is_(None),
        )
        .scalar()
        or 0
    )
    incidents_for_normal_predictions = int(
        db.query(func.count(NetworkIncident.id))
        .join(
            NetworkPrediction,
            NetworkIncident.prediction_id == NetworkPrediction.id,
        )
        .filter(
            NetworkIncident.dataset_id == dataset_id,
            NetworkPrediction.predicted_binary == 0,
        )
        .scalar()
        or 0
    )
    return (
        prediction_count == flow_count
        and incident_count == attack_count
        and missing_attack_incidents == 0
        and incidents_for_normal_predictions == 0
    )


def _persist_analysis_batch(
    db,
    dataset_id: int,
    prediction_rows: list[dict[str, Any]],
    incident_templates: list[dict[str, Any]],
) -> None:
    """Bulk insert one batch while retaining a single outer transaction."""
    db.execute(insert(NetworkPrediction), prediction_rows)
    flow_ids = [row["flow_id"] for row in prediction_rows]
    prediction_ids = {
        flow_id: prediction_id
        for prediction_id, flow_id in (
            db.query(NetworkPrediction.id, NetworkPrediction.flow_id)
            .filter(
                NetworkPrediction.dataset_id == dataset_id,
                NetworkPrediction.flow_id.in_(flow_ids),
            )
            .all()
        )
    }
    if len(prediction_ids) != len(prediction_rows):
        raise RuntimeError(
            "Persisted prediction IDs did not match the current flow batch."
        )
    incident_rows = []
    for template in incident_templates:
        incident_rows.append(
            {
                **template,
                "prediction_id": prediction_ids[template["flow_id"]],
            }
        )
    if incident_rows:
        db.execute(insert(NetworkIncident), incident_rows)


def _safe_analysis_error(error: Exception) -> str:
    """Return a user-safe failure reason without paths or internal details."""
    error_name = type(error).__name__.lower()
    if "detector" in error_name or isinstance(error, FileNotFoundError):
        return "The frozen network detector could not be loaded or verified."
    if "integrity" in error_name:
        return "Analysis results could not be persisted safely."
    return "Network dataset analysis failed. No partial results were saved."


def _mark_failed(db, dataset_id: int, safe_error: str) -> None:
    """Persist failed status in a fresh transaction after child rollback."""
    dataset = db.get(NetworkDataset, dataset_id)
    if dataset is None:
        return
    dataset.analysis_status = "failed"
    dataset.analysis_error = safe_error
    dataset.analysis_completed_at = datetime.utcnow()
    db.commit()


def persisted_analysis_summary(
    db, dataset_id: int, reused_existing: bool = False
) -> dict[str, Any] | None:
    """Build a truthful summary entirely from persisted database state."""
    dataset = db.get(NetworkDataset, dataset_id)
    if dataset is None:
        return None
    total_flows = int(
        db.query(func.count(NetworkFlow.id))
        .filter(NetworkFlow.dataset_id == dataset_id)
        .scalar()
        or 0
    )
    stats = (
        db.query(
            func.count(NetworkPrediction.id),
            func.coalesce(
                func.sum(
                    case((NetworkPrediction.predicted_binary == 0, 1), else_=0)
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case((NetworkPrediction.predicted_binary == 1, 1), else_=0)
                ),
                0,
            ),
            func.min(NetworkPrediction.rf_attack_probability),
            func.max(NetworkPrediction.rf_attack_probability),
            func.avg(NetworkPrediction.rf_attack_probability),
        )
        .filter(NetworkPrediction.dataset_id == dataset_id)
        .one()
    )
    total_predictions = int(stats[0] or 0)
    predicted_normal = int(stats[1] or 0)
    predicted_attack = int(stats[2] or 0)
    total_incidents = int(
        db.query(func.count(NetworkIncident.id))
        .filter(NetworkIncident.dataset_id == dataset_id)
        .scalar()
        or 0
    )
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for severity, count in (
        db.query(NetworkIncident.severity, func.count(NetworkIncident.id))
        .filter(NetworkIncident.dataset_id == dataset_id)
        .group_by(NetworkIncident.severity)
        .all()
    ):
        if severity in severity_counts:
            severity_counts[severity] = int(count)

    model_version_row = (
        db.query(NetworkPrediction.model_version)
        .filter(NetworkPrediction.dataset_id == dataset_id)
        .order_by(NetworkPrediction.id.asc())
        .first()
    )
    benchmark_metrics = None
    if dataset.has_ground_truth and total_predictions:
        confusion = (
            db.query(
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(
                                    NetworkPrediction.actual_binary == 0,
                                    NetworkPrediction.predicted_binary == 0,
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(
                                    NetworkPrediction.actual_binary == 0,
                                    NetworkPrediction.predicted_binary == 1,
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(
                                    NetworkPrediction.actual_binary == 1,
                                    NetworkPrediction.predicted_binary == 0,
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(
                                    NetworkPrediction.actual_binary == 1,
                                    NetworkPrediction.predicted_binary == 1,
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
            )
            .filter(NetworkPrediction.dataset_id == dataset_id)
            .one()
        )
        true_negatives, false_positives, false_negatives, true_positives = (
            int(value or 0) for value in confusion
        )
        benchmark_metrics = _benchmark_metrics_from_counts(
            actual_normal=true_negatives + false_positives,
            actual_attack=false_negatives + true_positives,
            true_negatives=true_negatives,
            false_positives=false_positives,
            false_negatives=false_negatives,
            true_positives=true_positives,
        )

    return {
        "dataset_id": dataset.id,
        "filename": dataset.filename,
        "total_flows": total_flows,
        "total_predictions": total_predictions,
        "predicted_normal": predicted_normal,
        "predicted_attack": predicted_attack,
        "predicted_attack_percentage": _safe_rate(
            predicted_attack * 100, total_predictions
        ),
        "total_incidents": total_incidents,
        "severity_counts": severity_counts,
        "minimum_probability": float(stats[3]) if stats[3] is not None else None,
        "maximum_probability": float(stats[4]) if stats[4] is not None else None,
        "mean_probability": float(stats[5]) if stats[5] is not None else None,
        "model_name": dataset.model_name,
        "model_version": model_version_row[0] if model_version_row else None,
        "threshold": dataset.model_threshold,
        "analysis_status": dataset.analysis_status,
        "analysis_error": dataset.analysis_error,
        "analysis_started_at": dataset.analysis_started_at,
        "analysis_completed_at": dataset.analysis_completed_at,
        "reused_existing": reused_existing,
        "benchmark_metrics": benchmark_metrics,
    }


def analyze_network_dataset(db, dataset_id: int) -> dict[str, Any]:
    """Run the frozen detector synchronously and persist one atomic result set."""
    dataset = (
        db.query(NetworkDataset)
        .filter(NetworkDataset.id == dataset_id)
        .with_for_update()
        .first()
    )
    if dataset is None:
        raise NetworkAnalysisNotFoundError("Network dataset not found")
    flow_count = int(
        db.query(func.count(NetworkFlow.id))
        .filter(NetworkFlow.dataset_id == dataset_id)
        .scalar()
        or 0
    )
    if flow_count == 0:
        raise NetworkAnalysisNoFlowsError(
            "Network dataset contains no stored flows."
        )
    if dataset.analysis_status == "processing":
        raise NetworkAnalysisConflictError(
            "Network dataset analysis is already processing."
        )
    if dataset.analysis_status == "completed":
        if not _completed_state_is_consistent(db, dataset_id, flow_count):
            raise NetworkAnalysisConflictError(
                "Completed network dataset has inconsistent prediction or "
                "incident records."
            )
        return persisted_analysis_summary(
            db, dataset_id, reused_existing=True
        )

    existing_predictions, _, existing_incidents = _child_counts(db, dataset_id)
    if existing_predictions or existing_incidents:
        raise NetworkAnalysisConflictError(
            "Dataset has residual analysis records and cannot be analysed safely."
        )

    dataset.analysis_status = "processing"
    dataset.analysis_error = None
    dataset.analysis_started_at = datetime.utcnow()
    dataset.analysis_completed_at = None
    db.commit()

    # This synchronous implementation is intentionally batched. Production-scale
    # execution should later move to workers with a job queue and progress polling.
    try:
        _, metadata = load_final_detector()
        model_name = str(metadata["selected_model_name"])
        model_version = str(metadata["artifact_sha256"])
        if float(metadata["selected_threshold"]) != ATTACK_THRESHOLD:
            raise RuntimeError("Frozen detector threshold metadata is inconsistent.")

        processed = 0
        predicted_attack_total = 0
        last_row_number = 0
        while processed < flow_count:
            flows = (
                db.query(NetworkFlow)
                .filter(
                    NetworkFlow.dataset_id == dataset_id,
                    NetworkFlow.row_number > last_row_number,
                )
                .order_by(NetworkFlow.row_number.asc())
                .limit(ANALYSIS_BATCH_SIZE)
                .all()
            )
            if not flows:
                raise RuntimeError(
                    "Stored flow count changed during network analysis."
                )
            feature_frame = pd.DataFrame(
                [
                    {
                        column: getattr(flow, column)
                        for column in FEATURE_COLUMNS
                    }
                    for flow in flows
                ],
                columns=FEATURE_COLUMNS,
            )
            predictions = predict_network_flows(feature_frame)
            if len(predictions) != len(flows):
                raise RuntimeError(
                    "Frozen detector returned an unexpected prediction count."
                )
            summary_frame = predictions.copy()
            if dataset.has_ground_truth:
                labels = [flow.actual_label for flow in flows]
                if any(label is None for label in labels):
                    raise RuntimeError(
                        "Labelled dataset contains a flow without ground truth."
                    )
                summary_frame[LABEL_COLUMN] = labels
            # Use the verified shared summary logic for each bounded batch.
            summarize_predictions(summary_frame)

            created_at = datetime.utcnow()
            prediction_rows: list[dict[str, Any]] = []
            incident_templates: list[dict[str, Any]] = []
            for flow, prediction in zip(
                flows, predictions.to_dict(orient="records")
            ):
                probability = float(prediction["rf_attack_probability"])
                predicted_binary = int(prediction["predicted_binary"])
                predicted_class = str(prediction["predicted_class"])
                actual_binary = None
                is_correct = None
                if dataset.has_ground_truth:
                    actual_binary = 0 if flow.actual_label == "normal" else 1
                    is_correct = actual_binary == predicted_binary
                prediction_rows.append(
                    {
                        "dataset_id": dataset_id,
                        "flow_id": flow.id,
                        "created_at": created_at,
                        "rf_attack_probability": probability,
                        "predicted_binary": predicted_binary,
                        "predicted_class": predicted_class,
                        "threshold_used": ATTACK_THRESHOLD,
                        "model_name": model_name,
                        "model_version": model_version,
                        "is_correct": is_correct,
                        "actual_binary": actual_binary,
                    }
                )
                if predicted_binary == 1:
                    predicted_attack_total += 1
                    incident_templates.append(
                        {
                            "dataset_id": dataset_id,
                            "flow_id": flow.id,
                            "created_at": created_at,
                            "incident_type": INCIDENT_TYPE,
                            "severity": severity_for_probability(probability),
                            "risk_score": probability * 100,
                            "evidence": build_incident_evidence(
                                flow, probability
                            ),
                            "recommended_action": RECOMMENDED_ACTION,
                            "status": "open",
                            "protocol_type": flow.protocol_type,
                            "service": flow.service,
                            "flag": flow.flag,
                            "actual_label": (
                                flow.actual_label
                                if dataset.has_ground_truth
                                else None
                            ),
                            "actual_family": (
                                flow.actual_family
                                if dataset.has_ground_truth
                                else None
                            ),
                        }
                    )
            _persist_analysis_batch(
                db,
                dataset_id,
                prediction_rows,
                incident_templates,
            )
            processed += len(flows)
            last_row_number = flows[-1].row_number

        persisted_predictions, persisted_attacks, persisted_incidents = (
            _child_counts(db, dataset_id)
        )
        if (
            processed != flow_count
            or persisted_predictions != flow_count
            or persisted_attacks != predicted_attack_total
            or persisted_incidents != predicted_attack_total
        ):
            raise RuntimeError(
                "Persisted analysis counts failed final consistency checks."
            )

        dataset = db.get(NetworkDataset, dataset_id)
        dataset.analysis_status = "completed"
        dataset.analysis_error = None
        dataset.analysis_completed_at = datetime.utcnow()
        dataset.model_name = model_name
        dataset.model_threshold = ATTACK_THRESHOLD
        db.commit()
    except Exception as error:
        db.rollback()
        safe_error = _safe_analysis_error(error)
        LOGGER.exception("Network dataset analysis failed")
        try:
            _mark_failed(db, dataset_id, safe_error)
        except Exception:
            db.rollback()
            LOGGER.exception("Could not persist failed network analysis status")
        raise NetworkAnalysisExecutionError(safe_error) from error

    return persisted_analysis_summary(db, dataset_id, reused_existing=False)
