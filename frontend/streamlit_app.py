import pandas as pd
import requests
import streamlit as st


API_BASE_URL = "http://127.0.0.1:8000"
INCIDENT_STATUSES = ["open", "investigating", "resolved", "false_positive"]


def check_backend_health():
    try:
        response = requests.get(f"{API_BASE_URL}/", timeout=5)
        response.raise_for_status()
        return True, response.json()
    except requests.RequestException as exc:
        return False, str(exc)


def upload_logs(uploaded_file):
    try:
        files = {
            "file": (
                uploaded_file.name,
                uploaded_file.getvalue(),
                "text/csv",
            )
        }
        response = requests.post(
            f"{API_BASE_URL}/logs/upload",
            files=files,
            timeout=30,
        )
        response.raise_for_status()
        return True, response.json()
    except requests.RequestException as exc:
        error_message = _get_error_message(exc)
        return False, error_message


def get_log_files():
    try:
        response = requests.get(f"{API_BASE_URL}/logs/files", timeout=10)
        response.raise_for_status()
        return True, response.json()
    except requests.RequestException as exc:
        return False, _get_error_message(exc)


def get_raw_logs(file_id, limit):
    try:
        response = requests.get(
            f"{API_BASE_URL}/logs",
            params={"file_id": file_id, "limit": limit},
            timeout=20,
        )
        response.raise_for_status()
        return True, response.json()
    except requests.RequestException as exc:
        return False, _get_error_message(exc)


def generate_ip_features(file_id):
    try:
        response = requests.post(
            f"{API_BASE_URL}/features/generate/{file_id}",
            timeout=30,
        )
        response.raise_for_status()
        return True, response.json()
    except requests.RequestException as exc:
        return False, _get_error_message(exc)


def get_ip_features(file_id):
    try:
        response = requests.get(
            f"{API_BASE_URL}/features/{file_id}",
            timeout=20,
        )
        response.raise_for_status()
        return True, response.json()
    except requests.RequestException as exc:
        return False, _get_error_message(exc)


def run_ml_anomaly_detection(file_id):
    try:
        response = requests.post(
            f"{API_BASE_URL}/ml/run/{file_id}",
            timeout=30,
        )
        response.raise_for_status()
        return True, response.json()
    except requests.RequestException as exc:
        return False, _get_error_message(exc)


def get_ml_scores(file_id):
    try:
        response = requests.get(
            f"{API_BASE_URL}/ml/scores/{file_id}",
            timeout=20,
        )
        response.raise_for_status()
        return True, response.json()
    except requests.RequestException as exc:
        return False, _get_error_message(exc)


def generate_incidents(file_id):
    try:
        response = requests.post(
            f"{API_BASE_URL}/incidents/generate/{file_id}",
            timeout=30,
        )
        response.raise_for_status()
        return True, response.json()
    except requests.RequestException as exc:
        return False, _get_error_message(exc)


def get_incidents(file_id=None):
    try:
        params = {}

        if file_id is not None:
            params["file_id"] = file_id

        response = requests.get(
            f"{API_BASE_URL}/incidents",
            params=params,
            timeout=20,
        )
        response.raise_for_status()
        return True, response.json()
    except requests.RequestException as exc:
        return False, _get_error_message(exc)


def update_incident_status(incident_id, status):
    try:
        response = requests.patch(
            f"{API_BASE_URL}/incidents/{incident_id}/status",
            json={"status": status},
            timeout=10,
        )
        response.raise_for_status()
        return True, response.json()
    except requests.RequestException as exc:
        return False, _get_error_message(exc)


def _get_error_message(exc):
    response = getattr(exc, "response", None)

    if response is None:
        return str(exc)

    try:
        return response.json()
    except ValueError:
        return response.text


def show_dataframe(data, columns=None):
    dataframe = pd.DataFrame(data)

    if columns is not None and not dataframe.empty:
        available_columns = [column for column in columns if column in dataframe.columns]
        dataframe = dataframe[available_columns]

    st.dataframe(dataframe, use_container_width=True)


st.set_page_config(
    page_title="Athes Sentinel",
    layout="wide",
)

st.title("Athes Sentinel")
st.caption("Lightweight log anomaly detection and incident monitoring dashboard.")


if "log_files" not in st.session_state:
    st.session_state.log_files = []

if "incidents" not in st.session_state:
    st.session_state.incidents = []

if "ip_features" not in st.session_state:
    st.session_state.ip_features = []

if "ml_scores" not in st.session_state:
    st.session_state.ml_scores = []


st.header("Backend Health Check")
is_healthy, health_result = check_backend_health()

if is_healthy:
    st.success("Backend is reachable.")
    st.json(health_result)
else:
    st.error("Backend is not running or cannot be reached.")
    st.write(health_result)


st.header("Upload Logs")
uploaded_file = st.file_uploader("Choose a CSV log file", type=["csv"])

if st.button("Upload CSV"):
    if uploaded_file is None:
        st.warning("Please choose a CSV file first.")
    else:
        success, upload_result = upload_logs(uploaded_file)

        if success:
            st.success("CSV uploaded successfully.")
            st.metric("File ID", upload_result["file_id"])
            st.write("Filename:", upload_result["filename"])
            st.write("Rows inserted:", upload_result["rows_inserted"])
        else:
            st.error("Upload failed.")
            st.write(upload_result)


st.header("Uploaded Log Files")

if st.button("Refresh log files"):
    success, log_files_result = get_log_files()

    if success:
        st.session_state.log_files = log_files_result
    else:
        st.error("Could not load uploaded log files.")
        st.write(log_files_result)

if st.session_state.log_files:
    show_dataframe(st.session_state.log_files)
    file_options = [log_file["id"] for log_file in st.session_state.log_files]
    selected_file_id = st.selectbox("Choose file_id", file_options)
else:
    selected_file_id = st.number_input(
        "Enter file_id",
        min_value=1,
        step=1,
        value=1,
    )


st.header("Raw Logs")
raw_log_limit = st.number_input(
    "Raw log limit",
    min_value=1,
    max_value=1000,
    value=100,
    step=10,
)

if st.button("Load raw logs"):
    success, raw_logs_result = get_raw_logs(selected_file_id, raw_log_limit)

    if success:
        if raw_logs_result:
            show_dataframe(raw_logs_result)
        else:
            st.info("No raw logs found for the selected file.")
    else:
        st.error("Could not load raw logs.")
        st.write(raw_logs_result)


st.header("Feature Generation")

if st.button("Generate IP Features"):
    success, feature_generation_result = generate_ip_features(selected_file_id)

    if success:
        st.success("IP feature generation completed.")
        st.write("File ID:", feature_generation_result["file_id"])
        st.write("IP count:", feature_generation_result["ip_count"])
        st.write("Features created:", feature_generation_result["features_created"])
    else:
        st.error("IP feature generation failed.")
        st.write(feature_generation_result)

if st.button("Load IP Features"):
    success, ip_features_result = get_ip_features(selected_file_id)

    if success:
        st.session_state.ip_features = ip_features_result
    else:
        st.error("Could not load IP features.")
        st.write(ip_features_result)

if st.session_state.ip_features:
    feature_columns = [
        "ip_address",
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
        "ml_anomaly_score",
    ]
    show_dataframe(st.session_state.ip_features, columns=feature_columns)
else:
    st.info("No IP features loaded yet.")


st.header("ML Anomaly Detection")
st.info(
    "Isolation Forest runs on the per-IP feature table. With very small "
    "datasets, ML scores may not be very meaningful yet."
)

if st.button("Run Isolation Forest"):
    success, ml_result = run_ml_anomaly_detection(selected_file_id)

    if success:
        st.success("Isolation Forest completed.")
        st.write("File ID:", ml_result["file_id"])
        st.write("IP count:", ml_result["ip_count"])
        st.write("Scores updated:", ml_result["scores_updated"])

        if ml_result.get("results"):
            show_dataframe(ml_result["results"])
    else:
        st.error("Isolation Forest failed.")
        st.write(ml_result)

if st.button("Load ML Scores"):
    success, ml_scores_result = get_ml_scores(selected_file_id)

    if success:
        st.session_state.ml_scores = ml_scores_result
    else:
        st.error("Could not load ML scores.")
        st.write(ml_scores_result)

if st.session_state.ml_scores:
    ml_score_columns = [
        "ip_address",
        "ml_anomaly_score",
        "total_requests",
        "error_rate",
        "endpoint_entropy",
        "request_frequency",
        "failed_login_count",
        "sensitive_endpoint_count",
    ]
    show_dataframe(st.session_state.ml_scores, columns=ml_score_columns)
else:
    st.info("No ML scores loaded yet.")

st.info(
    "Run Isolation Forest before generating incidents if you want incident "
    "risk_score to include the ML anomaly signal."
)


st.header("Incident Generation")
st.info(
    "Incident risk_score now combines rule score and ML anomaly score when ML "
    "scores are available."
)

if st.button("Generate Incidents"):
    success, generation_result = generate_incidents(selected_file_id)

    if success:
        st.success("Incident generation completed.")
        st.write("File ID:", generation_result["file_id"])
        st.write("Findings count:", generation_result["findings_count"])
        st.write("Incidents created:", generation_result["incidents_created"])

        if generation_result["incidents_created"] == 0:
            st.info("No suspicious activity crossed the configured rule thresholds.")
    else:
        st.error("Incident generation failed.")
        st.write(generation_result)


st.header("Incidents")

if st.button("Load incidents"):
    success, incidents_result = get_incidents(file_id=selected_file_id)

    if success:
        st.session_state.incidents = incidents_result
    else:
        st.error("Could not load incidents.")
        st.write(incidents_result)

if st.session_state.incidents:
    incident_columns = [
        "id",
        "ip_address",
        "incident_type",
        "severity",
        "risk_score",
        "evidence",
        "recommended_action",
        "status",
        "created_at",
    ]
    show_dataframe(st.session_state.incidents, columns=incident_columns)
else:
    st.info("No incidents loaded yet.")


st.header("Update Incident Status")

if st.session_state.incidents:
    incident_ids = [incident["id"] for incident in st.session_state.incidents]
    selected_incident_id = st.selectbox("Choose incident_id", incident_ids)
    selected_status = st.selectbox("Choose status", INCIDENT_STATUSES)

    if st.button("Update Status"):
        success, status_result = update_incident_status(
            selected_incident_id,
            selected_status,
        )

        if success:
            st.success("Incident status updated.")
            st.json(status_result)
        else:
            st.error("Could not update incident status.")
            st.write(status_result)
else:
    st.info("Load incidents first to update a status.")
