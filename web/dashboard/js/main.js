import {
  analyzeCsv,
  disconnectShopify,
  fetchAnalysisById,
  fetchAnalysisHistory,
  fetchCurrentUser,
  fetchShopifyStatus,
  logout,
  runShopifyMonitorNow,
  startShopifyConnect,
} from "./api.js";
import { TOKEN_STORAGE_KEY } from "./config.js";
import { renderAnalysis, renderHistoryList, renderUploadEvent, resetFeed } from "./render.js";

const feed = document.getElementById("analysis-feed");
const empty = document.getElementById("feed-empty");
const form = document.getElementById("upload-form");
const fileInput = document.getElementById("csv-file");
const dropZone = document.getElementById("drop-zone");
const statusEl = document.getElementById("status");
const historyListEl = document.getElementById("history-list");
const runButton = form ? form.querySelector("button[type='submit']") : null;
const userNameEl = document.getElementById("user-name");
const userCardNameEl = document.getElementById("user-card-name");
const userCardEmailEl = document.getElementById("user-card-email");
const userToggleBtn = document.getElementById("user-toggle");
const userActionsEl = document.getElementById("user-actions");
const logoutBtn = document.getElementById("logout-btn");
const shopDomainInputEl = document.getElementById("shop-domain-input");
const shopifyConnectBtn = document.getElementById("shopify-connect-btn");
const shopifyDisconnectBtn = document.getElementById("shopify-disconnect-btn");
const shopifySyncBtn = document.getElementById("shopify-sync-btn");
const shopifyStatusEl = document.getElementById("shopify-status");
const accountMenuButtons = document.querySelectorAll(".account-link[data-account-action]");
let currentRunId = null;

function runIdToConversationId(runId) {
  const numeric = Number(runId);
  if (!Number.isFinite(numeric) || numeric <= 0) return null;
  return `r${numeric.toString(36)}`;
}

function conversationIdToRunId(conversationId) {
  if (!conversationId || typeof conversationId !== "string") return null;
  if (!/^r[0-9a-z]+$/i.test(conversationId)) return null;
  const runId = Number.parseInt(conversationId.slice(1), 36);
  return Number.isFinite(runId) && runId > 0 ? runId : null;
}

function readConversationIdFromHash() {
  const hash = window.location.hash || "";
  const match = hash.match(/^#\/c\/([A-Za-z0-9_-]+)$/);
  return match ? match[1] : null;
}

function updateConversationUrl(runId) {
  const conversationId = runIdToConversationId(runId);
  if (!conversationId) return;

  const onBackendRoute = window.location.port === "8000";
  const nextUrl = onBackendRoute ? `/c/${conversationId}` : `#/c/${conversationId}`;
  window.history.replaceState({}, "", nextUrl);
}

function redirectToLogin() {
  window.location.href = "/login/";
}

function requireAuthToken() {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY);
  if (!token) {
    redirectToLogin();
    return null;
  }
  return token;
}

function setStatus(message, isError = false) {
  if (!statusEl) return;
  statusEl.textContent = message;
  statusEl.classList.toggle("error", isError);
}

function pickFile(file) {
  if (!fileInput || !file) return;
  if (!file.name.toLowerCase().endsWith(".csv")) {
    setStatus("Please select a valid .csv file.", true);
    return;
  }
  const dt = new DataTransfer();
  dt.items.add(file);
  fileInput.files = dt.files;
  setStatus(`Ready: ${file.name}`);
}

function setRunningState(isRunning) {
  if (!runButton) return;
  runButton.disabled = isRunning;
  runButton.textContent = isRunning ? "Running..." : "Run Analysis";
}

function setShopifyStatus(message, isError = false) {
  if (!shopifyStatusEl) return;
  shopifyStatusEl.textContent = message;
  shopifyStatusEl.classList.toggle("error", isError);
}

function setShopifyButtonsDisabled(disabled) {
  [shopifyConnectBtn, shopifyDisconnectBtn, shopifySyncBtn].forEach((button) => {
    if (button) button.disabled = disabled;
  });
}

function closeUserFlyout() {
  if (!userActionsEl || !userToggleBtn) return;
  userActionsEl.hidden = true;
  userToggleBtn.setAttribute("aria-expanded", "false");
}

function toggleUserFlyout() {
  if (!userActionsEl || !userToggleBtn) return;
  const isOpen = !userActionsEl.hidden;
  userActionsEl.hidden = isOpen;
  userToggleBtn.setAttribute("aria-expanded", String(!isOpen));
}

async function loadShopifyStatus() {
  try {
    const status = await fetchShopifyStatus();
    if (!status.connected) {
      setShopifyStatus("No Shopify connection yet.");
      return;
    }

    if (shopDomainInputEl && status.shop_domain) {
      shopDomainInputEl.value = status.shop_domain;
    }

    const synced = status.last_synced_at ? ` Last sync: ${status.last_synced_at}.` : "";
    setShopifyStatus(`Connected: ${status.shop_domain || "store"}.${synced}`);
  } catch (error) {
    if (error.message === "AUTH_REQUIRED") {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
      redirectToLogin();
      return;
    }
    setShopifyStatus(error.message || "Failed to fetch Shopify status.", true);
  }
}

function showSingleAnalysis(payload, fileName = null) {
  resetFeed(feed);
  if (fileName) {
    renderUploadEvent(feed, fileName);
  }
  renderAnalysis(feed, payload);
  feed.scrollTop = feed.scrollHeight;
  currentRunId = payload?.run_id ?? null;
  if (currentRunId) {
    updateConversationUrl(currentRunId);
  }
}

async function loadHistory() {
  try {
    const rows = await fetchAnalysisHistory(20);
    renderHistoryList(historyListEl, rows, async (runId) => {
      if (currentRunId === runId) {
        setStatus(`Run #${runId} is already open.`);
        return;
      }
      setStatus(`Loading run #${runId}...`);
      try {
        const payload = await fetchAnalysisById(runId);
        showSingleAnalysis(payload);
        setStatus(`Loaded run #${runId}.`);
      } catch (error) {
        if (error.message === "AUTH_REQUIRED") {
          localStorage.removeItem(TOKEN_STORAGE_KEY);
          redirectToLogin();
          return;
        }
        setStatus(error.message || "Failed to load saved analysis.", true);
      }
    });
  } catch (error) {
    if (error.message === "AUTH_REQUIRED") {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
      redirectToLogin();
      return;
    }
    setStatus(error.message || "Failed to load history.", true);
  }
}

if (dropZone) {
  ["dragenter", "dragover"].forEach((eventName) => {
    dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropZone.classList.add("dragover");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropZone.classList.remove("dragover");
    });
  });

  dropZone.addEventListener("drop", (event) => {
    const file = event.dataTransfer?.files?.[0];
    if (file) pickFile(file);
  });
}

if (form) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const file = fileInput?.files?.[0];
    if (!file) {
      setStatus("Please add a CSV file first.", true);
      return;
    }

    if (!file.name.toLowerCase().endsWith(".csv")) {
      setStatus("Only .csv files are supported right now.", true);
      return;
    }

    setRunningState(true);
    currentRunId = null;
    resetFeed(feed);
    renderUploadEvent(feed, file.name);
    setStatus("Running analysis...");

    try {
      const payload = await analyzeCsv(file);
      showSingleAnalysis(payload, file.name);
      if (payload.from_cache) {
        setStatus("Loaded existing analysis for this same CSV content.");
      } else {
        setStatus("Analysis complete.");
      }
      await loadHistory();
    } catch (error) {
      if (error.message === "AUTH_REQUIRED") {
        localStorage.removeItem(TOKEN_STORAGE_KEY);
        redirectToLogin();
        return;
      }
      setStatus(error.message || "Analysis failed.", true);
    } finally {
      setRunningState(false);
    }
  });
}

if (fileInput) {
  fileInput.addEventListener("change", () => {
    const file = fileInput.files?.[0];
    if (!file) {
      setStatus("Please add a CSV file first.", true);
      return;
    }
    if (!file.name.toLowerCase().endsWith(".csv")) {
      setStatus("Only .csv files are supported right now.", true);
      return;
    }
    setStatus(`Ready: ${file.name}`);
  });
}

if (logoutBtn) {
  logoutBtn.addEventListener("click", async () => {
    try {
      await logout();
    } catch (_err) {
      // Continue local logout even if API call fails.
    } finally {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
      redirectToLogin();
    }
  });
}

if (shopifyConnectBtn) {
  shopifyConnectBtn.addEventListener("click", async () => {
    const shopDomain = shopDomainInputEl?.value?.trim();
    if (!shopDomain) {
      setShopifyStatus("Enter your Shopify domain first.", true);
      return;
    }

    setShopifyButtonsDisabled(true);
    setShopifyStatus("Preparing Shopify connection...");
    try {
      const result = await startShopifyConnect(shopDomain);
      window.location.href = result.auth_url;
    } catch (error) {
      if (error.message === "AUTH_REQUIRED") {
        localStorage.removeItem(TOKEN_STORAGE_KEY);
        redirectToLogin();
        return;
      }
      setShopifyStatus(error.message || "Failed to start Shopify connect flow.", true);
      setShopifyButtonsDisabled(false);
    }
  });
}

if (shopifyDisconnectBtn) {
  shopifyDisconnectBtn.addEventListener("click", async () => {
    setShopifyButtonsDisabled(true);
    try {
      await disconnectShopify();
      if (shopDomainInputEl) shopDomainInputEl.value = "";
      setShopifyStatus("Shopify connection removed.");
    } catch (error) {
      if (error.message === "AUTH_REQUIRED") {
        localStorage.removeItem(TOKEN_STORAGE_KEY);
        redirectToLogin();
        return;
      }
      setShopifyStatus(error.message || "Failed to disconnect Shopify.", true);
    } finally {
      setShopifyButtonsDisabled(false);
    }
  });
}

if (shopifySyncBtn) {
  shopifySyncBtn.addEventListener("click", async () => {
    setShopifyButtonsDisabled(true);
    setShopifyStatus("Running monitor now...");
    try {
      const result = await runShopifyMonitorNow();
      setShopifyStatus(`Monitor complete. Analyses: ${result.triggered_analyses}.`);
      await loadHistory();
      await loadShopifyStatus();
    } catch (error) {
      if (error.message === "AUTH_REQUIRED") {
        localStorage.removeItem(TOKEN_STORAGE_KEY);
        redirectToLogin();
        return;
      }
      setShopifyStatus(error.message || "Failed to run monitor.", true);
    } finally {
      setShopifyButtonsDisabled(false);
    }
  });
}

accountMenuButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const action = button.getAttribute("data-account-action");
    switch (action) {
      case "settings":
        if (shopDomainInputEl) {
          shopDomainInputEl.focus();
        }
        setShopifyStatus("Settings opened. Update your Shopify connection here.");
        break;
      case "profile":
        setStatus("Profile view is available from the account flyout.");
        break;
      case "help":
        setStatus("Help: connect Shopify, then use Sync Now to run monitoring.");
        break;
      case "upgrade":
        setStatus("Upgrade plan is coming soon.");
        break;
      case "personalization":
        setStatus("Personalization will be added to this account menu.");
        break;
      default:
        break;
    }
  });
});

if (userToggleBtn && userActionsEl) {
  userToggleBtn.addEventListener("click", toggleUserFlyout);
}

document.addEventListener("click", (event) => {
  if (!userActionsEl || !userToggleBtn) return;
  const target = event.target;
  if (!(target instanceof Node)) return;
  if (userActionsEl.hidden) return;
  if (userToggleBtn.contains(target) || userActionsEl.contains(target)) return;
  closeUserFlyout();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeUserFlyout();
  }
});

async function bootstrap() {
  const token = requireAuthToken();
  if (!token) {
    return;
  }

  try {
    const me = await fetchCurrentUser();
    if (userNameEl) {
      const fallbackName = typeof me.email === "string" ? me.email.split("@")[0] : "User";
      userNameEl.textContent = me.full_name || fallbackName;
    }
    if (userCardNameEl) {
      const fallbackName = typeof me.email === "string" ? me.email.split("@")[0] : "User";
      userCardNameEl.textContent = me.full_name || fallbackName;
    }
    if (userCardEmailEl) {
      userCardEmailEl.textContent = typeof me.email === "string" ? me.email : "";
    }
    await loadHistory();
    await loadShopifyStatus();

    const conversationId = readConversationIdFromHash();
    if (conversationId) {
      const runId = conversationIdToRunId(conversationId);
      if (runId && runId !== currentRunId) {
        try {
          const payload = await fetchAnalysisById(runId);
          showSingleAnalysis(payload);
          setStatus(`Loaded run #${runId} from conversation URL.`);
        } catch (_error) {
          setStatus("Conversation URL is invalid or no longer available.", true);
        }
      }
    }
  } catch (error) {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    redirectToLogin();
  }
}

bootstrap();
