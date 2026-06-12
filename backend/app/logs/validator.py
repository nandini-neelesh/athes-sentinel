import pandas as pd


REQUIRED_COLUMNS = [
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


def validate_log_dataframe(df):
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in df.columns]

    if missing_columns:
        missing_text = ", ".join(missing_columns)
        raise ValueError(f"Missing required CSV columns: {missing_text}")

    cleaned_df = df.copy()

    required_values = [
        "timestamp",
        "ip_address",
        "endpoint",
        "method",
        "status_code",
        "response_time_ms",
    ]

    if cleaned_df[required_values].isna().any().any():
        raise ValueError("Required CSV values cannot be empty.")

    try:
        cleaned_df["timestamp"] = pd.to_datetime(
            cleaned_df["timestamp"],
            errors="raise",
        )
    except Exception as exc:
        raise ValueError("Invalid timestamp values. Use a valid datetime format.") from exc

    try:
        status_codes = pd.to_numeric(
            cleaned_df["status_code"],
            errors="raise",
        )

        if (status_codes % 1 != 0).any():
            raise ValueError

        cleaned_df["status_code"] = status_codes.astype(int)
    except Exception as exc:
        raise ValueError("Invalid status_code values. Use whole numbers only.") from exc

    try:
        response_times = pd.to_numeric(
            cleaned_df["response_time_ms"],
            errors="raise",
        )
        cleaned_df["response_time_ms"] = response_times.astype(float)
    except Exception as exc:
        raise ValueError("Invalid response_time_ms values. Use numeric values only.") from exc

    return cleaned_df
