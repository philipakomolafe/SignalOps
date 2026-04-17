import { fetchCurrentUser, login, requestPasswordReset, resetPassword, signup } from "./api.js";

const TOKEN_STORAGE_KEY = "signalops_access_token";
const RESUME_CHECKOUT_KEY = "signalops_resume_checkout";

const signinForm = document.getElementById("signin-form");
const registerForm = document.getElementById("register-form");
const forgotForm = document.getElementById("forgot-form");
const resetForm = document.getElementById("reset-form");
const statusEl = document.getElementById("status");
const signinBtn = document.getElementById("signin-btn");
const registerBtn = document.getElementById("register-btn");
const forgotBtn = document.getElementById("forgot-btn");
const resetBtn = document.getElementById("reset-btn");
const successEl = document.getElementById("success");
const tabs = Array.from(document.querySelectorAll(".tab"));
const panels = Array.from(document.querySelectorAll(".tab-panel"));
const forgotPasswordLink = document.getElementById("forgot-password-link");
const forgotBackBtn = document.getElementById("forgot-back-btn");
const resetBackBtn = document.getElementById("reset-back-btn");
const resetLinkPreviewEl = document.getElementById("reset-link-preview");
const resetTokenInput = document.getElementById("reset-token");

let isRedirectingToDashboard = false;

function postAuthDestination() {
  const params = new URLSearchParams(window.location.search);
  const next = (params.get("next") || "").trim();
  if (!next) {
    try {
      const raw = sessionStorage.getItem(RESUME_CHECKOUT_KEY);
      if (!raw) {
        return "/dashboard/";
      }
      const parsed = JSON.parse(raw);
      const plan = String(parsed && parsed.plan ? parsed.plan : "starter").trim().toLowerCase();
      const safePlan = plan === "pro" ? "pro" : "starter";
      const returnPath = String(parsed && parsed.returnPath ? parsed.returnPath : "").trim();
      let resumePath = `/buy/?plan=${encodeURIComponent(safePlan)}&resume=1`;
      if (returnPath && returnPath.charAt(0) === "/" && returnPath.slice(0, 2) !== "//") {
        resumePath += `&return=${encodeURIComponent(returnPath)}`;
      }
      return resumePath;
    } catch (_error) {
      return "/dashboard/";
    }
  }

  // Allow only same-origin absolute paths to avoid open redirects.
  if (next.charAt(0) !== "/" || next.slice(0, 2) === "//") {
    return "/dashboard/";
  }
  return next;
}

function setStatus(message, isError = false) {
  if (!statusEl) return;
  statusEl.textContent = message;
  statusEl.classList.toggle("error", isError);
}

function activateTab(tabName) {
  tabs.forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.tabTarget === tabName);
  });
  panels.forEach((panel) => {
    const isActive = panel.dataset.tabPanel === tabName;
    panel.classList.toggle("active", isActive);
    panel.hidden = !isActive;
  });
}

function setAuxPanel(mode) {
  const next = String(mode || "none").toLowerCase();
  if (forgotForm) forgotForm.hidden = next !== "forgot";
  if (resetForm) resetForm.hidden = next !== "reset";
  if (next === "none") {
    panels.forEach((panel) => {
      panel.hidden = !panel.classList.contains("active");
    });
    return;
  }

  if (signinForm) signinForm.hidden = true;
  if (registerForm) registerForm.hidden = true;
  if (successEl) successEl.hidden = true;
}

function setSubmitting(button, isSubmitting, busyLabel, idleLabel) {
  if (!button) return;
  button.disabled = isSubmitting;
  button.textContent = isSubmitting ? busyLabel : idleLabel;
}

function goToDashboard() {
  if (isRedirectingToDashboard) return;
  isRedirectingToDashboard = true;
  // replace() prevents keeping login as a sticky destination in browser history.
  window.location.replace(postAuthDestination());
}

async function redirectIfSessionIsActive() {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY);
  if (!token) {
    return;
  }

  try {
    await fetchCurrentUser(token);
    goToDashboard();
  } catch (_error) {
    // Invalid/expired sessions should not lock users out of login.
    localStorage.removeItem(TOKEN_STORAGE_KEY);
  }
}

tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    activateTab(tab.dataset.tabTarget || "signin");
    setAuxPanel("none");
    if (successEl) successEl.hidden = true;
    setStatus("");
  });
});

if (forgotPasswordLink) {
  forgotPasswordLink.addEventListener("click", () => {
    activateTab("signin");
    setAuxPanel("forgot");
    setStatus("");
    if (resetLinkPreviewEl) {
      resetLinkPreviewEl.hidden = true;
      resetLinkPreviewEl.textContent = "";
    }
  });
}

if (forgotBackBtn) {
  forgotBackBtn.addEventListener("click", () => {
    setAuxPanel("none");
    activateTab("signin");
    setStatus("");
  });
}

if (resetBackBtn) {
  resetBackBtn.addEventListener("click", () => {
    setAuxPanel("none");
    activateTab("signin");
    setStatus("");
    const url = new URL(window.location.href);
    url.searchParams.delete("reset_token");
    window.history.replaceState({}, "", url.pathname + url.search + url.hash);
  });
}

if (signinForm) {
  signinForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!signinForm.reportValidity()) {
      return;
    }

    const payload = {
      email: signinForm.email.value.trim(),
      password: signinForm.password.value,
    };

    setSubmitting(signinBtn, true, "Signing in...", "Sign in with Email");
    setStatus("Signing in...");

    try {
      const result = await login(payload);
      localStorage.setItem(TOKEN_STORAGE_KEY, result.access_token);
      setStatus("Login successful. Redirecting...");
      goToDashboard();
    } catch (error) {
      setStatus(error.message || "Login failed.", true);
    } finally {
      setSubmitting(signinBtn, false, "Signing in...", "Sign in with Email");
    }
  });
}

if (registerForm) {
  registerForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!registerForm.reportValidity()) {
      return;
    }

    const payload = {
      full_name: registerForm.full_name.value.trim(),
      email: registerForm.email.value.trim(),
      company: registerForm.company.value.trim() || null,
      password: registerForm.password.value,
    };

    setSubmitting(registerBtn, true, "Creating...", "Create account with Email");
    setStatus("Creating your account...");

    try {
      await signup(payload);
      registerForm.reset();
      if (successEl) successEl.hidden = false;
      setStatus("Account created. Please sign in.");
      activateTab("signin");
    } catch (error) {
      setStatus(error.message || "Signup failed.", true);
    } finally {
      setSubmitting(registerBtn, false, "Creating...", "Create account with Email");
    }
  });
}

if (forgotForm) {
  forgotForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!forgotForm.reportValidity()) {
      return;
    }

    const payload = { email: forgotForm.email.value.trim() };
    setSubmitting(forgotBtn, true, "Sending...", "Send reset link");
    setStatus("Generating reset link...");
    if (resetLinkPreviewEl) {
      resetLinkPreviewEl.hidden = true;
      resetLinkPreviewEl.textContent = "";
    }

    try {
      const result = await requestPasswordReset(payload);
      setStatus(result.message || "If the account exists, a reset link has been generated.");
      if (result.reset_url && resetLinkPreviewEl) {
        resetLinkPreviewEl.hidden = false;
        resetLinkPreviewEl.innerHTML = `Reset link (dev): <a href="${result.reset_url}">Open reset page</a>`;
      }
    } catch (error) {
      setStatus(error.message || "Failed to request password reset.", true);
    } finally {
      setSubmitting(forgotBtn, false, "Sending...", "Send reset link");
    }
  });
}

if (resetForm) {
  resetForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!resetForm.reportValidity()) {
      return;
    }

    const token = String(resetForm.token.value || "").trim();
    const password = String(resetForm.new_password.value || "");
    const confirm = String(resetForm.confirm_password.value || "");
    if (!token) {
      setStatus("Reset token is missing. Request a new password reset link.", true);
      return;
    }
    if (password !== confirm) {
      setStatus("Password confirmation does not match.", true);
      return;
    }

    setSubmitting(resetBtn, true, "Updating...", "Update password");
    setStatus("Updating password...");
    try {
      const result = await resetPassword({ token, new_password: password });
      resetForm.reset();
      if (resetTokenInput) resetTokenInput.value = "";
      setAuxPanel("none");
      activateTab("signin");
      setStatus(result.message || "Password updated. Sign in with your new password.");
      const url = new URL(window.location.href);
      url.searchParams.delete("reset_token");
      window.history.replaceState({}, "", url.pathname + url.search + url.hash);
    } catch (error) {
      setStatus(error.message || "Failed to reset password.", true);
    } finally {
      setSubmitting(resetBtn, false, "Updating...", "Update password");
    }
  });
}

const params = new URLSearchParams(window.location.search);
const resetTokenFromUrl = (params.get("reset_token") || "").trim();
if (resetTokenFromUrl && resetTokenInput) {
  activateTab("signin");
  resetTokenInput.value = resetTokenFromUrl;
  setAuxPanel("reset");
} else if (window.location.hash === "#register") {
  activateTab("register");
  setAuxPanel("none");
} else {
  activateTab("signin");
  setAuxPanel("none");
}

redirectIfSessionIsActive();
