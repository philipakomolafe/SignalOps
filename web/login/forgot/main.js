import { requestPasswordReset } from "../js/api.js";

const form = document.getElementById("forgot-form");
const statusEl = document.getElementById("status");
const submitBtn = document.getElementById("forgot-submit-btn");
const resendBtn = document.getElementById("forgot-resend-btn");
const emailInput = document.getElementById("forgot-email");

function setStatus(message, isError = false) {
  if (!statusEl) return;
  statusEl.textContent = message;
  statusEl.classList.toggle("error", isError);
}

function setSubmitting(isSubmitting) {
  if (!submitBtn) return;
  submitBtn.disabled = isSubmitting;
  submitBtn.textContent = isSubmitting ? "Sending..." : "Send Link";
}

async function triggerForgot() {
  if (!form || !emailInput) return;
  if (!form.reportValidity()) return;

  const email = String(emailInput.value || "").trim();
  if (!email) {
    setStatus("Please enter your email.", true);
    return;
  }

  setSubmitting(true);
  setStatus("Sending password reset link...");
  try {
    const result = await requestPasswordReset({ email });
    setStatus(result.message || "If an account exists for this email, a reset link has been sent.");
    if (resendBtn) resendBtn.disabled = false;
  } catch (error) {
    setStatus(error.message || "Password reset request failed.", true);
  } finally {
    setSubmitting(false);
  }
}

if (form) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    await triggerForgot();
  });
}

if (resendBtn) {
  resendBtn.addEventListener("click", async () => {
    await triggerForgot();
  });
}

const params = new URLSearchParams(window.location.search);
const prefillEmail = String(params.get("email") || "").trim();
if (emailInput && prefillEmail) {
  emailInput.value = prefillEmail;
}
