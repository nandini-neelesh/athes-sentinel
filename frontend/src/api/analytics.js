import apiClient from "./client.js";

export async function getSummary(fileId) {
  const response = await apiClient.get(`/analytics/summary/${fileId}`);

  return response.data;
}

export async function getStatusCodeDistribution(fileId) {
  const response = await apiClient.get(`/analytics/status-codes/${fileId}`);

  return response.data;
}

export async function getTopIps(fileId, limit = 10) {
  const response = await apiClient.get(`/analytics/top-ips/${fileId}`, {
    params: { limit },
  });

  return response.data;
}

export async function getHourlyTraffic(fileId) {
  const response = await apiClient.get(`/analytics/hourly-traffic/${fileId}`);

  return response.data;
}

export async function getTopEndpoints(fileId, limit = 10) {
  const response = await apiClient.get(`/analytics/top-endpoints/${fileId}`, {
    params: { limit },
  });

  return response.data;
}

export async function getSlowestEndpoints(fileId, limit = 10) {
  const response = await apiClient.get(
    `/analytics/slowest-endpoints/${fileId}`,
    {
      params: { limit },
    }
  );

  return response.data;
}

export async function getErrorRateByEndpoint(fileId, limit = 10) {
  const response = await apiClient.get(
    `/analytics/error-rate-by-endpoint/${fileId}`,
    {
      params: { limit },
    }
  );

  return response.data;
}
