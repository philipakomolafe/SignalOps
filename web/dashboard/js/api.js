import { ANALYSIS_ENDPOINT, API_BASE, SEGMENT, TOKEN_STORAGE_KEY } from "./config.js";

const HISTORY_ENDPOINT = `${ANALYSIS_ENDPOINT.replace("/analyze", "")}/history`;
const ME_ENDPOINT = `${API_BASE}/api/v1/auth/me`;
const LOGOUT_ENDPOINT = `${API_BASE}/api/v1/auth/logout`;
const SHOPIFY_CONNECT_START_ENDPOINT = `${API_BASE}/api/v1/integrations/shopify/connect/start`;
const SHOPIFY_STATUS_ENDPOINT = `${API_BASE}/api/v1/integrations/shopify/status`;
const SHOPIFY_DISCONNECT_ENDPOINT = `${API_BASE}/api/v1/integrations/shopify/disconnect`;
const SHOPIFY_MONITOR_NOW_ENDPOINT = `${API_BASE}/api/v1/integrations/shopify/monitor-now`;
const ACCOUNT_PLAN_ENDPOINT = `${API_BASE}/api/v1/account/plan`;
const USER_PERFORMANCE_ENDPOINT = `${API_BASE}/api/v1/srl/performance`;
const ACTION_FEEDBACK_ENDPOINT = `${API_BASE}/api/v1/srl/action-feedback`;

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

export async function startShopifyConnect(shopDomain) {
  const response = await fetch(SHOPIFY_CONNECT_START_ENDPOINT, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ shop_domain: shopDomain }),
  });
  return parseResponse(response, "Failed to start Shopify connection.");
}

export async function fetchShopifyStatus() {
  const response = await fetch(SHOPIFY_STATUS_ENDPOINT, {
    headers: authHeaders(),
  });
  return parseResponse(response, "Failed to fetch Shopify status.");
}

export async function disconnectShopify() {
  const response = await fetch(SHOPIFY_DISCONNECT_ENDPOINT, {
    method: "POST",
    headers: authHeaders(),
  });
  return parseResponse(response, "Failed to disconnect Shopify.");
}

export async function runShopifyMonitorNow() {
  const response = await fetch(SHOPIFY_MONITOR_NOW_ENDPOINT, {
    method: "POST",
    headers: authHeaders(),
  });
  return parseResponse(response, "Failed to run Shopify monitor.");
}

export async function fetchAccountPlan() {
  const response = await fetch(ACCOUNT_PLAN_ENDPOINT, {
    headers: authHeaders(),
  });
  return parseResponse(response, "Failed to fetch account plan.");
}

export async function fetchUserPerformance(days = 7) {
  const response = await fetch(`${USER_PERFORMANCE_ENDPOINT}?days=${encodeURIComponent(String(days))}`, {
    headers: authHeaders(),
  });
  return parseResponse(response, "Failed to fetch performance data.");
}

export async function submitActionFeedback(actionTaken, actionDate, selfReportedOutcome) {
  const response = await fetch(ACTION_FEEDBACK_ENDPOINT, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      action_taken: actionTaken,
      action_date: actionDate,
      self_reported_outcome: selfReportedOutcome,
    }),
  });
  return parseResponse(response, "Failed to save action feedback.");
}
