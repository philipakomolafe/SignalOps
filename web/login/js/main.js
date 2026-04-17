import { fetchCurrentUser, login, signup } from "./api.js";

const TOKEN_STORAGE_KEY = "signalops_access_token";
const RESUME_CHECKOUT_KEY = "signalops_resume_checkout";

const signinForm = document.getElementById("signin-form");
const registerForm = document.getElementById("register-form");
const statusEl = document.getElementById("status");
const signinBtn = document.getElementById("signin-btn");
const registerBtn = document.getElementById("register-btn");
const successEl = document.getElementById("success");
const forgotPasswordLinkEl = document.getElementById("forgot-password-link");
const tabs = Array.from(document.querySelectorAll(".tab"));
const panels = Array.from(document.querySelectorAll(".tab-panel"));

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

const params = new URLSearchParams(window.location.search);
if ((params.get("reset") || "").trim().toLowerCase() === "ok") {
  setStatus("Password updated. You can sign in now.");
}

if (forgotPasswordLinkEl && signinForm) {
  forgotPasswordLinkEl.addEventListener("click", (event) => {
    event.preventDefault();
    const emailValue = String(signinForm.email?.value || "").trim();
    const nextUrl = emailValue
      ? `/login/forgot/?email=${encodeURIComponent(emailValue)}`
      : "/login/forgot/";
    window.location.href = nextUrl;
  });
}

redirectIfSessionIsActive();
