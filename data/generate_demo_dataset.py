from datetime import datetime, timedelta
from pathlib import Path
import random

import pandas as pd


random.seed(42)


OUTPUT_PATH = Path("data/mixed_realistic_logs.csv")
CSV_COLUMNS = [
    "timestamp",
    "ip_address",
    "user_id",
    "endpoint",
    "method",
    "status_code",
    "response_time_ms",
    "event_type",
    "user_agent",
]

START_TIME = datetime(2026, 6, 17, 9, 0, 0)
WINDOW_MINUTES = 180

NORMAL_ENDPOINTS = [
    "/",
    "/home",
    "/login",
    "/logout",
    "/dashboard",
    "/profile",
    "/products",
    "/cart",
    "/checkout",
    "/api/orders",
    "/api/products",
]

RARE_NORMAL_ENDPOINTS = [
    "/settings",
]

USER_AGENTS = [
    "Mozilla/5.0 Chrome/125.0",
    "Mozilla/5.0 Firefox/126.0",
    "Mozilla/5.0 Edg/125.0",
    "Mozilla/5.0 Safari/17.5",
    "curl/8.4.0",
]

SUSPICIOUS_IPS = {
    "brute_force": "10.10.10.10",
    "endpoint_scanning": "10.10.10.20",
    "unauthorized_access": "10.10.10.30",
    "error_spike": "10.10.10.40",
    "slow_response": "10.10.10.50",
}


def random_timestamp(start_time, window_minutes):
    seconds = random.randint(0, window_minutes * 60)
    return start_time + timedelta(seconds=seconds)


def format_timestamp(timestamp):
    return timestamp.strftime("%Y-%m-%d %H:%M:%S")


def make_row(
    timestamp,
    ip_address,
    user_id,
    endpoint,
    method,
    status_code,
    response_time_ms,
    event_type,
    user_agent,
):
    return {
        "timestamp": format_timestamp(timestamp),
        "ip_address": ip_address,
        "user_id": user_id,
        "endpoint": endpoint,
        "method": method,
        "status_code": status_code,
        "response_time_ms": round(response_time_ms, 2),
        "event_type": event_type,
        "user_agent": user_agent,
    }


def event_type_for_normal_request(endpoint, status_code):
    if endpoint == "/login" and status_code == 200:
        return "login_success"

    if endpoint == "/logout":
        return "logout"

    if endpoint == "/checkout":
        return "checkout"

    if endpoint == "/profile" and random.random() < 0.25:
        return "profile_update"

    if endpoint.startswith("/api/"):
        return "api_request"

    return "page_view"


def method_for_endpoint(endpoint):
    if endpoint == "/login":
        return "POST"

    if endpoint == "/logout":
        return "POST"

    if endpoint == "/checkout":
        return "POST"

    if endpoint.startswith("/api/"):
        return random.choice(["GET", "POST"])

    return "GET"


def generate_normal_rows():
    rows = []
    normal_ips = [f"192.168.{index // 255}.{index % 255}" for index in range(10, 70)]

    for index, ip_address in enumerate(normal_ips):
        user_id = f"user_{1000 + index}"

        # Normal users repeat a small set of common paths instead of scanning widely.
        endpoint_pool = ["/", "/home", "/login", "/dashboard", "/profile"]

        if index % 3 == 0:
            endpoint_pool.extend(["/products", "/cart", "/checkout"])
        elif index % 3 == 1:
            endpoint_pool.extend(["/api/orders", "/api/products", "/products"])
        else:
            endpoint_pool.extend(["/products", "/api/products", "/logout"])

        request_count = random.randint(14, 18)

        for _ in range(request_count):
            endpoint = random.choice(endpoint_pool)
            status_code = random.choices(
                population=[200, 302, 404, 500],
                weights=[93, 5, 1.5, 0.5],
                k=1,
            )[0]
            timestamp = random_timestamp(START_TIME, WINDOW_MINUTES)
            response_time = max(80, min(random.gauss(300, 125), 800))

            rows.append(
                make_row(
                    timestamp=timestamp,
                    ip_address=ip_address,
                    user_id=user_id,
                    endpoint=endpoint,
                    method=method_for_endpoint(endpoint),
                    status_code=status_code,
                    response_time_ms=response_time,
                    event_type=event_type_for_normal_request(endpoint, status_code),
                    user_agent=random.choice(USER_AGENTS),
                )
            )

        # A few normal users visit settings once, but not enough to trip rules.
        if random.random() < 0.18:
            endpoint = random.choice(RARE_NORMAL_ENDPOINTS)
            timestamp = random_timestamp(START_TIME, WINDOW_MINUTES)

            rows.append(
                make_row(
                    timestamp=timestamp,
                    ip_address=ip_address,
                    user_id=user_id,
                    endpoint=endpoint,
                    method=method_for_endpoint(endpoint),
                    status_code=200,
                    response_time_ms=random.uniform(120, 520),
                    event_type="page_view",
                    user_agent=random.choice(USER_AGENTS),
                )
            )

    return rows


def generate_brute_force_rows():
    rows = []
    start_time = START_TIME + timedelta(minutes=22)

    # Many failed login attempts in a short burst should trigger brute force.
    for index in range(45):
        timestamp = start_time + timedelta(seconds=index * random.randint(5, 15))
        status_code = random.choice([401, 401, 401, 403])

        rows.append(
            make_row(
                timestamp=timestamp,
                ip_address=SUSPICIOUS_IPS["brute_force"],
                user_id=f"target_{random.randint(1, 5)}",
                endpoint="/login",
                method="POST",
                status_code=status_code,
                response_time_ms=random.uniform(90, 260),
                event_type="login_failed",
                user_agent=random.choice(["curl/8.4.0", "Mozilla/5.0 Chrome/125.0"]),
            )
        )

    return rows


def generate_endpoint_scanning_rows():
    rows = []
    start_time = START_TIME + timedelta(minutes=55)
    scan_endpoints = [
        "/admin",
        "/config",
        "/.env",
        "/api/users",
        "/settings",
        "/wp-admin",
        "/phpmyadmin",
        "/server-status",
        "/backup",
        "/debug",
        "/admin/login",
        "/admin/config",
        "/api/private",
        "/api/token",
        "/uploads",
        "/old",
        "/test",
        "/vendor",
        "/.git/config",
        "/robots.txt",
        "/sitemap.xml",
        "/console",
        "/actuator",
        "/actuator/env",
        "/manager/html",
        "/shell",
        "/login",
        "/dbadmin",
        "/portal",
        "/internal",
    ]

    # Broad path probing with many 403 and 404 responses should look like scanning.
    for index in range(90):
        endpoint = random.choice(scan_endpoints)
        timestamp = start_time + timedelta(seconds=index * random.randint(8, 20))

        rows.append(
            make_row(
                timestamp=timestamp,
                ip_address=SUSPICIOUS_IPS["endpoint_scanning"],
                user_id="",
                endpoint=endpoint,
                method=random.choice(["GET", "HEAD"]),
                status_code=random.choice([403, 404, 404, 404, 200]),
                response_time_ms=random.uniform(100, 700),
                event_type="page_view",
                user_agent=random.choice(["curl/8.4.0", "Mozilla/5.0 Firefox/126.0"]),
            )
        )

    return rows


def generate_unauthorized_access_rows():
    rows = []
    start_time = START_TIME + timedelta(minutes=88)
    protected_endpoints = ["/admin", "/settings", "/api/users"]

    # Repeated access to protected areas with 403 responses.
    for index in range(55):
        endpoint = random.choice(protected_endpoints)
        timestamp = start_time + timedelta(seconds=index * random.randint(12, 30))

        rows.append(
            make_row(
                timestamp=timestamp,
                ip_address=SUSPICIOUS_IPS["unauthorized_access"],
                user_id=f"user_{random.randint(2000, 2005)}",
                endpoint=endpoint,
                method=random.choice(["GET", "POST"]),
                status_code=random.choice([403, 403, 403, 404]),
                response_time_ms=random.uniform(120, 500),
                event_type="api_request" if endpoint.startswith("/api/") else "page_view",
                user_agent=random.choice(USER_AGENTS),
            )
        )

    return rows


def generate_error_spike_rows():
    rows = []
    start_time = START_TIME + timedelta(minutes=120)
    endpoints = ["/api/orders", "/api/products", "/checkout", "/dashboard"]

    # A high share of server errors should trigger the error spike rule.
    for index in range(60):
        endpoint = random.choice(endpoints)
        timestamp = start_time + timedelta(seconds=index * random.randint(15, 35))

        rows.append(
            make_row(
                timestamp=timestamp,
                ip_address=SUSPICIOUS_IPS["error_spike"],
                user_id=f"user_{random.randint(3000, 3004)}",
                endpoint=endpoint,
                method=method_for_endpoint(endpoint),
                status_code=random.choice([500, 500, 503, 503, 200]),
                response_time_ms=random.uniform(400, 1400),
                event_type="api_request",
                user_agent=random.choice(USER_AGENTS),
            )
        )

    return rows


def generate_slow_response_rows():
    rows = []
    start_time = START_TIME + timedelta(minutes=145)
    endpoints = ["/dashboard", "/api/orders", "/checkout", "/profile"]

    # Long response times should trigger the slow response rule.
    for index in range(55):
        endpoint = random.choice(endpoints)
        timestamp = start_time + timedelta(seconds=index * random.randint(18, 40))

        if index % 8 == 0:
            response_time = random.uniform(7200, 9500)
        else:
            response_time = random.uniform(3200, 6800)

        rows.append(
            make_row(
                timestamp=timestamp,
                ip_address=SUSPICIOUS_IPS["slow_response"],
                user_id=f"user_{random.randint(4000, 4004)}",
                endpoint=endpoint,
                method=method_for_endpoint(endpoint),
                status_code=random.choice([200, 200, 200, 500]),
                response_time_ms=response_time,
                event_type="api_request" if endpoint.startswith("/api/") else "page_view",
                user_agent=random.choice(USER_AGENTS),
            )
        )

    return rows


def build_dataset():
    rows = []
    rows.extend(generate_normal_rows())
    rows.extend(generate_brute_force_rows())
    rows.extend(generate_endpoint_scanning_rows())
    rows.extend(generate_unauthorized_access_rows())
    rows.extend(generate_error_spike_rows())
    rows.extend(generate_slow_response_rows())

    random.shuffle(rows)

    dataframe = pd.DataFrame(rows, columns=CSV_COLUMNS)
    dataframe["timestamp"] = pd.to_datetime(dataframe["timestamp"])
    dataframe = dataframe.sort_values("timestamp")
    dataframe["timestamp"] = dataframe["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")

    return dataframe


def print_summary(dataframe):
    print(f"Output path: {OUTPUT_PATH}")
    print(f"Total rows: {len(dataframe)}")
    print(f"Unique IPs: {dataframe['ip_address'].nunique()}")
    print("Suspicious IP summary:")

    summaries = {
        SUSPICIOUS_IPS["brute_force"]: "brute force login failures",
        SUSPICIOUS_IPS["endpoint_scanning"]: "endpoint scanning and sensitive paths",
        SUSPICIOUS_IPS["unauthorized_access"]: "repeated unauthorized access",
        SUSPICIOUS_IPS["error_spike"]: "server error spike",
        SUSPICIOUS_IPS["slow_response"]: "slow response behavior",
    }

    for ip_address, description in summaries.items():
        row_count = len(dataframe[dataframe["ip_address"] == ip_address])
        print(f"- {ip_address}: {row_count} rows, {description}")


def main():
    dataframe = build_dataset()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(OUTPUT_PATH, index=False)
    print_summary(dataframe)


if __name__ == "__main__":
    main()
