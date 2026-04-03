import { fetchCurrentUser, login, signup } from "./api.js";

const TOKEN_STORAGE_KEY = "signalops_access_token";

const signinForm = document.getElementById("signin-form");
const registerForm = document.getElementById("register-form");
const statusEl = document.getElementById("status");
const signinBtn = document.getElementById("signin-btn");
const registerBtn = document.getElementById("register-btn");
const successEl = document.getElementById("success");
const tabs = Array.from(document.querySelectorAll(".tab"));
const panels = Array.from(document.querySelectorAll(".tab-panel"));

let isRedirectingToDashboard = false;

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

function setSubmitting(button, isSubmitting, busyLabel, idleLabel) {
  if (!button) return;
  button.disabled = isSubmitting;
  button.textContent = isSubmitting ? busyLabel : idleLabel;
}

function goToDashboard() {
  if (isRedirectingToDashboard) return;
  isRedirectingToDashboard = true;
  // replace() prevents keeping login as a sticky destination in browser history.
  window.location.replace("/dashboard/");
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
    if (successEl) successEl.hidden = true;
    setStatus("");
  });
});

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

if (window.location.hash === "#register") {
  activateTab("register");
} else {
  activateTab("signin");
}

redirectIfSessionIsActive();
