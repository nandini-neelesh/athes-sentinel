import apiClient from "./client.js";

export async function getLogFiles() {
  const response = await apiClient.get("/logs/files");

  return response.data;
}

export async function uploadLogFile(file) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await apiClient.post("/logs/upload", formData);

  return response.data;
}
