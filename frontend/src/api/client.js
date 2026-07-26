import axios from "axios";

const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();

if (import.meta.env.PROD && !configuredApiBaseUrl) {
  throw new Error(
    "VITE_API_BASE_URL must be configured for a production frontend."
  );
}

const apiBaseUrl =
  configuredApiBaseUrl ||
  (import.meta.env.DEV ? "http://127.0.0.1:8000" : undefined);

const apiClient = axios.create({
  baseURL: apiBaseUrl,
});

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("athes_token");

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
});

export default apiClient;
