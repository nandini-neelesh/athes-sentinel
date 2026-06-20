import apiClient from "./client.js";

export async function getIncidents(fileId) {
  const response = await apiClient.get("/incidents", {
    params: { file_id: fileId },
  });

  return response.data;
}

export async function updateIncidentStatus(incidentId, status) {
  const response = await apiClient.patch(`/incidents/${incidentId}/status`, {
    status,
  });

  return response.data;
}
