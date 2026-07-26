import apiClient from "./client.js";

export async function uploadNetworkDataset(file) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await apiClient.post("/network/datasets/upload", formData);

  return response.data;
}

export async function getNetworkDatasets({ limit = 50, offset = 0 } = {}) {
  const response = await apiClient.get("/network/datasets", {
    params: { limit, offset },
  });

  return response.data;
}

export async function getNetworkDataset(datasetId) {
  const response = await apiClient.get(`/network/datasets/${datasetId}`);

  return response.data;
}

export async function getNetworkFlows(
  datasetId,
  { limit = 100, offset = 0 } = {}
) {
  const response = await apiClient.get(
    `/network/datasets/${datasetId}/flows`,
    {
      params: { limit, offset },
    }
  );

  return response.data;
}

export async function analyzeNetworkDataset(datasetId) {
  const response = await apiClient.post(
    `/network/datasets/${datasetId}/analyze`
  );

  return response.data;
}

export async function getNetworkAnalysis(datasetId) {
  const response = await apiClient.get(
    `/network/datasets/${datasetId}/analysis`
  );

  return response.data;
}

export async function getNetworkDashboard(datasetId) {
  const response = await apiClient.get(
    `/network/datasets/${datasetId}/dashboard`
  );

  return response.data;
}

export async function getNetworkAnalytics(
  datasetId,
  { serviceLimit = 10 } = {}
) {
  const response = await apiClient.get(
    `/network/datasets/${datasetId}/analytics`,
    {
      params: { service_limit: serviceLimit },
    }
  );

  return response.data;
}

export async function getNetworkIncidents(datasetId, options = {}) {
  const {
    limit = 50,
    offset = 0,
    status,
    severity,
    search,
  } = options;
  const params = { limit, offset };

  if (typeof status === "string" && status.trim()) {
    params.status = status.trim();
  }

  if (typeof severity === "string" && severity.trim()) {
    params.severity = severity.trim();
  }

  if (typeof search === "string" && search.trim()) {
    params.search = search.trim();
  }

  const response = await apiClient.get(
    `/network/datasets/${datasetId}/incidents`,
    { params }
  );

  return response.data;
}

export async function getNetworkIncident(incidentId) {
  const response = await apiClient.get(`/network/incidents/${incidentId}`);

  return response.data;
}

export async function updateNetworkIncidentStatus(incidentId, status) {
  const response = await apiClient.patch(
    `/network/incidents/${incidentId}/status`,
    { status }
  );

  return response.data;
}
