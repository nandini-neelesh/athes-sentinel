import apiClient from "./client.js";

export async function getSummary(fileId) {
  const response = await apiClient.get(`/analytics/summary/${fileId}`);

  return response.data;
}
