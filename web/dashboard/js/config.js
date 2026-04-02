export const API_BASE = (window.SIGNALOPS_API_BASE || window.location.origin || "").replace(/\/$/, "");
export const ANALYSIS_ENDPOINT = `${API_BASE}/api/v1/srl/analyze`;
export const SEGMENT = "shopify-5k-25k";
export const TOKEN_STORAGE_KEY = "signalops_access_token";
