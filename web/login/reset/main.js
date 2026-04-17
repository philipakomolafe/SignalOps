import { resetPassword } from "../js/api.js";

const form = document.getElementById("reset-form");
const statusEl = document.getElementById("status");
const submitBtn = document.getElementById("reset-submit-btn");
const newPasswordInput = document.getElementById("new-password");
const confirmPasswordInput = document.getElementById("confirm-password");

function setStatus(message, isError = false) {
  if (!statusEl) return;
  statusEl.textContent = message;
  statusEl.classList.toggle("error", isError);
}

function setSubmitting(isSubmitting) {
  if (!submitBtn) return;
  submitBtn.disabled = isSubmitting;
  submitBtn.textContent = isSubmitting ? "Updating..." : "Update Password";
}

const token = String(new URLSearchParams(window.location.search).get("token") || "").trim();
if (!token) {
  if (form) form.hidden = true;
  setStatus("Reset link is missing or invalid. Request a new link.", true);
}

if (form) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!token) return;
    if (!form.reportValidity()) return;

    const newPassword = String(newPasswordInput?.value || "");
    const confirmPassword = String(confirmPasswordInput?.value || "");
    if (newPassword !== confirmPassword) {
      setStatus("Passwords do not match.", true);
      return;
    }

    setSubmitting(true);
    setStatus("Updating password...");
    try {
      const result = await resetPassword({ token, new_password: newPassword });
      setStatus(result.message || "Password updated. Redirecting to sign in...");
      window.setTimeout(() => {
        window.location.href = "/login/?reset=ok";
      }, 900);
    } catch (error) {
      setStatus(error.message || "Reset failed. Request a new link.", true);
    } finally {
      setSubmitting(false);
    }
  });
}
