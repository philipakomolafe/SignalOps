const API_BASE = (window.SIGNALOPS_API_BASE || window.location.origin || "").replace(/\/$/, "");
const LOGIN_ENDPOINT = `${API_BASE}/api/v1/auth/login`;
const SIGNUP_ENDPOINT = `${API_BASE}/api/v1/auth/signup`;
const ME_ENDPOINT = `${API_BASE}/api/v1/auth/me`;
const FORGOT_PASSWORD_ENDPOINT = `${API_BASE}/api/v1/auth/password/forgot`;
const RESET_PASSWORD_ENDPOINT = `${API_BASE}/api/v1/auth/password/reset`;

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

export async function fetchCurrentUser(accessToken) {
  const response = await fetch(ME_ENDPOINT, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  });

  const data = await response.json();
  if (!response.ok) {
    const detail = data && data.detail ? data.detail : "Session check failed.";
    throw new Error(detail);
  }

  return data;
}

export async function requestPasswordReset(payload) {
  const response = await fetch(FORGOT_PASSWORD_ENDPOINT, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  const data = await response.json();
  if (!response.ok) {
    const detail = data && data.detail ? data.detail : "Password reset request failed.";
    throw new Error(detail);
  }

  return data;
}

export async function resetPassword(payload) {
  const response = await fetch(RESET_PASSWORD_ENDPOINT, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  const data = await response.json();
  if (!response.ok) {
    const detail = data && data.detail ? data.detail : "Password reset failed.";
    throw new Error(detail);
  }

  return data;
}
