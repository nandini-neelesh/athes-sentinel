import apiClient from "./client.js";

export async function generateFeatures(fileId) {
  const response = await apiClient.post(`/features/generate/${fileId}`);

  return response.data;
}

export async function runMlScoring(fileId) {
  const response = await apiClient.post(`/ml/run/${fileId}`);

  return response.data;
}

export async function generateIncidents(fileId) {
  const response = await apiClient.post(`/incidents/generate/${fileId}`);

  return response.data;
}
