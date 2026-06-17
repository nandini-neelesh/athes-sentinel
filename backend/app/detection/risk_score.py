def clamp_score(value):
    if value is None:
        return 0.0

    score = float(value)

    if score < 0:
        return 0.0

    if score > 100:
        return 100.0

    return score


def calculate_unified_risk_score(rule_score, ml_anomaly_score):
    rule_score = clamp_score(rule_score)

    if ml_anomaly_score is None:
        return round(rule_score, 2)

    ml_anomaly_score = clamp_score(ml_anomaly_score)
    unified_score = 0.7 * rule_score + 0.3 * ml_anomaly_score

    return round(clamp_score(unified_score), 2)


def severity_from_risk_score(risk_score):
    risk_score = clamp_score(risk_score)

    if risk_score <= 24:
        return "low"

    if risk_score <= 59:
        return "medium"

    if risk_score <= 84:
        return "high"

    return "critical"


def build_risk_explanation(rule_score, ml_anomaly_score, unified_score):
    if ml_anomaly_score is None:
        return "Risk score based on rule score only because ML score was not available."

    return (
        f"Risk score combines rule score {clamp_score(rule_score):.2f} "
        f"and ML anomaly score {clamp_score(ml_anomaly_score):.2f}. "
        f"Final unified risk score is {clamp_score(unified_score):.2f}."
    )
