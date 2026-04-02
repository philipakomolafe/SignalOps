const API_BASE = (window.SIGNALOPS_API_BASE || window.location.origin || "").replace(/\/$/, "");
const LOGIN_ENDPOINT = `${API_BASE}/api/v1/auth/login`;
const SIGNUP_ENDPOINT = `${API_BASE}/api/v1/auth/signup`;

export async function login(payload) {
  const response = await fetch(LOGIN_ENDPOINT, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  const data = await response.json();
  if (!response.ok) {
    const detail = data && data.detail ? data.detail : "Login failed.";
    throw new Error(detail);
  }

  return data;
}

export async function signup(payload) {
  const response = await fetch(SIGNUP_ENDPOINT, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  const data = await response.json();
  if (!response.ok) {
    const detail = data && data.detail ? data.detail : "Signup failed.";
    throw new Error(detail);
  }

  return data;
}
