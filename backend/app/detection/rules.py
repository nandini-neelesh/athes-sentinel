from backend.app.database.models import IPFeature
from backend.app.detection.rule_config import RULE_CONFIG


# TODO: Add suspicious night activity after IPFeature has night_hour_request_ratio.


def _safe_number(value, default=0):
    if value is None:
        return default

    return value


def _score_for_severity(severity):
    return RULE_CONFIG["score_values"][severity]


def _reduce_severity(severity):
    if severity == "critical":
        return "high"

    if severity == "high":
        return "medium"

    if severity == "medium":
        return None

    return severity


def build_finding(
    ip_feature,
    rule_name,
    incident_type,
    severity,
    rule_score,
    evidence,
    recommended_action,
):
    return {
        "file_id": ip_feature.file_id,
        "ip_address": ip_feature.ip_address,
        "rule_name": rule_name,
        "incident_type": incident_type,
        "severity": severity,
        "rule_score": rule_score,
        "evidence": evidence,
        "recommended_action": recommended_action,
        "source": "rule",
    }


def detect_brute_force(ip_feature):
    config = RULE_CONFIG["brute_force"]

    failed_logins = _safe_number(ip_feature.failed_login_count)
    successful_logins = _safe_number(ip_feature.success_login_count)
    request_frequency = _safe_number(ip_feature.request_frequency, 0.0)

    if failed_logins < config["medium_failed_logins"]:
        return None

    if failed_logins >= config["critical_failed_logins"]:
        severity = "critical"
    elif (
        failed_logins >= config["high_failed_logins"]
        or request_frequency >= config["high_request_frequency"]
    ):
        severity = "high"
    else:
        severity = "medium"

    # A later successful login can mean a real user eventually typed correctly.
    if successful_logins > 0 and config["reduce_if_successful_login"]:
        severity = _reduce_severity(severity)

        if severity is None:
            return None

    evidence = (
        f"{failed_logins} failed login attempts, {successful_logins} successful "
        f"logins, request frequency {request_frequency:.2f} requests/min."
    )

    return build_finding(
        ip_feature=ip_feature,
        rule_name="brute_force",
        incident_type="Possible brute force login activity",
        severity=severity,
        rule_score=_score_for_severity(severity),
        evidence=evidence,
        recommended_action="Review login attempts for this IP and consider rate limiting or temporary blocking.",
    )


def detect_unauthorized_access(ip_feature):
    config = RULE_CONFIG["unauthorized_access"]

    error_4xx_count = _safe_number(ip_feature.error_4xx_count)
    sensitive_endpoint_count = _safe_number(ip_feature.sensitive_endpoint_count)

    repeated_4xx = error_4xx_count >= config["medium_4xx_errors"]
    many_4xx = error_4xx_count >= config["high_4xx_errors"]
    repeated_sensitive_hits = (
        sensitive_endpoint_count >= config["sensitive_endpoint_threshold"]
    )

    if not repeated_4xx and not repeated_sensitive_hits:
        return None

    if many_4xx or (repeated_4xx and repeated_sensitive_hits):
        severity = "high"
    else:
        severity = "medium"

    evidence = (
        f"{error_4xx_count} client error responses and "
        f"{sensitive_endpoint_count} sensitive endpoint requests."
    )

    return build_finding(
        ip_feature=ip_feature,
        rule_name="unauthorized_access",
        incident_type="Repeated unauthorized or forbidden access",
        severity=severity,
        rule_score=_score_for_severity(severity),
        evidence=evidence,
        recommended_action="Review requested endpoints and confirm whether this IP should have access.",
    )


def detect_error_spike(ip_feature):
    config = RULE_CONFIG["error_spike"]

    error_rate = _safe_number(ip_feature.error_rate, 0.0)
    error_4xx_count = _safe_number(ip_feature.error_4xx_count)
    error_5xx_count = _safe_number(ip_feature.error_5xx_count)
    total_errors = error_4xx_count + error_5xx_count

    if total_errors < config["minimum_error_count"]:
        return None

    if error_rate >= config["high_error_rate"]:
        severity = "high"
    elif error_rate >= config["medium_error_rate"]:
        severity = "medium"
    else:
        return None

    evidence = (
        f"Error rate {error_rate:.2f} with {error_4xx_count} 4xx errors "
        f"and {error_5xx_count} 5xx errors."
    )

    return build_finding(
        ip_feature=ip_feature,
        rule_name="error_spike",
        incident_type="High error response rate",
        severity=severity,
        rule_score=_score_for_severity(severity),
        evidence=evidence,
        recommended_action="Check whether this IP is probing invalid paths or triggering server-side failures.",
    )


def detect_endpoint_scanning(ip_feature):
    config = RULE_CONFIG["endpoint_scanning"]

    unique_endpoints = _safe_number(ip_feature.unique_endpoints)
    endpoint_entropy = _safe_number(ip_feature.endpoint_entropy, 0.0)
    error_4xx_count = _safe_number(ip_feature.error_4xx_count)

    enough_unique_endpoints = unique_endpoints >= config["medium_unique_endpoints"]
    many_unique_endpoints = unique_endpoints >= config["high_unique_endpoints"]
    high_entropy = endpoint_entropy >= config["entropy_threshold"]
    enough_errors = error_4xx_count >= config["minimum_4xx_errors"]

    if not enough_unique_endpoints:
        return None

    if not high_entropy and not enough_errors:
        return None

    if many_unique_endpoints and (high_entropy or enough_errors):
        severity = "high"
    else:
        severity = "medium"

    evidence = (
        f"{unique_endpoints} unique endpoints, endpoint entropy "
        f"{endpoint_entropy:.2f}, and {error_4xx_count} 4xx errors."
    )

    return build_finding(
        ip_feature=ip_feature,
        rule_name="endpoint_scanning",
        incident_type="Possible endpoint scanning",
        severity=severity,
        rule_score=_score_for_severity(severity),
        evidence=evidence,
        recommended_action="Review endpoint spread for this IP and look for path probing patterns.",
    )


def detect_slow_response(ip_feature):
    config = RULE_CONFIG["slow_response"]

    avg_response_time = _safe_number(ip_feature.avg_response_time, 0.0)
    max_response_time = _safe_number(ip_feature.max_response_time, 0.0)

    high_average = avg_response_time >= config["high_avg_response_ms"]
    high_maximum = max_response_time >= config["high_max_response_ms"]
    medium_average = avg_response_time >= config["medium_avg_response_ms"]
    medium_maximum = max_response_time >= config["medium_max_response_ms"]

    if high_average or high_maximum:
        severity = "high"
    elif medium_average or medium_maximum:
        severity = "medium"
    else:
        return None

    evidence = (
        f"Average response time {avg_response_time:.2f} ms and maximum "
        f"response time {max_response_time:.2f} ms."
    )

    return build_finding(
        ip_feature=ip_feature,
        rule_name="slow_response",
        incident_type="Unusually slow responses",
        severity=severity,
        rule_score=_score_for_severity(severity),
        evidence=evidence,
        recommended_action="Check whether this IP is associated with expensive requests or service degradation.",
    )


def detect_all_rules_for_feature(ip_feature):
    rule_functions = [
        detect_brute_force,
        detect_unauthorized_access,
        detect_error_spike,
        detect_endpoint_scanning,
        detect_slow_response,
    ]

    findings = []

    for rule_function in rule_functions:
        finding = rule_function(ip_feature)

        if finding is not None:
            findings.append(finding)

    return findings


def run_rule_engine_for_file(file_id, db):
    ip_features = db.query(IPFeature).filter(IPFeature.file_id == file_id).all()

    if not ip_features:
        raise ValueError(f"No IP feature rows found for file_id={file_id}.")

    findings = []

    for ip_feature in ip_features:
        findings.extend(detect_all_rules_for_feature(ip_feature))

    return findings
