RULE_CONFIG = {
    "brute_force": {
        "medium_failed_logins": 5,
        "high_failed_logins": 10,
        "critical_failed_logins": 20,
        "high_request_frequency": 30.0,
        "reduce_if_successful_login": True,
    },
    "unauthorized_access": {
        "medium_4xx_errors": 10,
        "high_4xx_errors": 25,
        "sensitive_endpoint_threshold": 3,
    },
    "error_spike": {
        "medium_error_rate": 0.25,
        "high_error_rate": 0.50,
        "minimum_error_count": 5,
    },
    "endpoint_scanning": {
        "medium_unique_endpoints": 10,
        "high_unique_endpoints": 25,
        "entropy_threshold": 2.5,
        "minimum_4xx_errors": 5,
    },
    "slow_response": {
        "medium_avg_response_ms": 1000.0,
        "high_avg_response_ms": 2500.0,
        "medium_max_response_ms": 3000.0,
        "high_max_response_ms": 7000.0,
    },
    "score_values": {
        "low": 25,
        "medium": 50,
        "high": 75,
        "critical": 95,
    },
}
