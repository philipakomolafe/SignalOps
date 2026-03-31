import { ANALYSIS_ENDPOINT, API_BASE, SEGMENT, TOKEN_STORAGE_KEY } from "./config.js";

const HISTORY_ENDPOINT = `${ANALYSIS_ENDPOINT.replace("/analyze", "")}/history`;
const ME_ENDPOINT = `${API_BASE}/api/v1/auth/me`;
const LOGOUT_ENDPOINT = `${API_BASE}/api/v1/auth/logout`;

function authHeaders(extraHeaders = {}) {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY);
  return token
    ? { ...extraHeaders, Authorization: `Bearer ${token}` }
    : { ...extraHeaders };
}

async function parseResponse(response, fallbackMessage) {
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : { detail: await response.text() };

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error("AUTH_REQUIRED");
    }
    const detail = payload && payload.detail ? payload.detail : fallbackMessage;
    throw new Error(detail);
  }

  return payload;
}

export async function analyzeCsv(file) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("segment", SEGMENT);

  const response = await fetch(ANALYSIS_ENDPOINT, {
    method: "POST",
    body: formData,
    headers: authHeaders(),
  });
  return parseResponse(response, "Analysis failed.");
}

export async function fetchAnalysisHistory(limit = 20) {
  const response = await fetch(`${HISTORY_ENDPOINT}?limit=${limit}`, {
    headers: authHeaders(),
  });
  return parseResponse(response, "Failed to fetch analysis history.");
}

export async function fetchAnalysisById(runId) {
  const response = await fetch(`${HISTORY_ENDPOINT}/${runId}`, {
    headers: authHeaders(),
  });
  return parseResponse(response, "Failed to fetch saved analysis.");
}

export async function fetchCurrentUser() {
  const response = await fetch(ME_ENDPOINT, {
    headers: authHeaders(),
  });
  return parseResponse(response, "Failed to fetch current user.");
}

export async function logout() {
  const response = await fetch(LOGOUT_ENDPOINT, {
    method: "POST",
    headers: authHeaders(),
  });
  return parseResponse(response, "Logout failed.");
}
