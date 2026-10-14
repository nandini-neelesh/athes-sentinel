import axios from "axios";

const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim().replace(
  /\/+$/,
  ""
);

// A production build without VITE_API_BASE_URL used to throw while the module
// loaded, which left a blank white page. Expose the problem instead so the
// login screen can explain it.
export const apiConfigError =
  import.meta.env.PROD && !configuredApiBaseUrl
    ? "This deployment is missing VITE_API_BASE_URL. Set it to the backend URL in the hosting dashboard and redeploy."
    : null;

const apiBaseUrl =
  configuredApiBaseUrl ||
  (import.meta.env.DEV ? "http://127.0.0.1:8000" : undefined);

const apiClient = axios.create({
  baseURL: apiBaseUrl,
});

apiClient.interceptors.request.use((config) => {
  if (apiConfigError) {
    return Promise.reject(new Error(apiConfigError));
  }

  const token = localStorage.getItem("athes_token");

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
});

export default apiClient;
