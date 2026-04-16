import {
  analyzeCsv,
  disconnectShopify,
  fetchAccountPlan,
  fetchAnalysisById,
  fetchAnalysisHistory,
  fetchCurrentUser,
  fetchUserPerformance,
  fetchShopifyStatus,
  logout,
  runShopifyMonitorNow,
  startShopifyConnect,
  submitActionFeedback,
} from "./api.js";
import { TOKEN_STORAGE_KEY } from "./config.js";
import {
  renderAnalysis,
  renderHistoryList,
  renderSidebarActionFeedback,
  renderSidebarPerformance,
  renderUploadEvent,
  resetFeed,
} from "./render.js";

const feed = document.getElementById("analysis-feed");
const form = document.getElementById("upload-form");
const fileInput = document.getElementById("csv-file");
const dropZone = document.getElementById("drop-zone");
const statusEl = document.getElementById("status");
const historyListEl = document.getElementById("history-list");
const runButton = form ? form.querySelector("button[type='submit']") : null;
const userNameEl = document.getElementById("user-name");
const userToggleBtn = document.getElementById("user-toggle");
const userActionsEl = document.getElementById("user-actions");
const sidebarUserEl = document.querySelector(".sidebar-user");
const logoutBtn = document.getElementById("logout-btn");

const shopDomainInputEl = document.getElementById("shop-domain-input");
const shopifyConnectBtn = document.getElementById("shopify-connect-btn");
const shopifyDisconnectBtn = document.getElementById("shopify-disconnect-btn");
const shopifySyncBtn = document.getElementById("shopify-sync-btn");
const shopifyStatusEl = document.getElementById("shopify-status");

const sidebarPerformanceContentEl = document.getElementById("sidebar-performance-content");
const sidebarFeedbackContentEl = document.getElementById("sidebar-feedback-content");
const sidebarHistorySectionEl = document.getElementById("sidebar-history-section");
const sidebarPerformanceSectionEl = document.getElementById("sidebar-performance-section");
const sidebarFeedbackSectionEl = document.getElementById("sidebar-feedback-section");
const sidebarNavEls = Array.from(document.querySelectorAll(".sidebar-nav-item"));
const planPillEl = document.getElementById("plan-pill");
const upgradeLinkEl = document.getElementById("upgrade-link");

const openSettingsBtn = document.getElementById("open-settings-btn");
const settingsModalEl = document.getElementById("settings-modal");
const settingsCloseBtn = document.getElementById("settings-close-btn");

let currentRunId = null;
let latestPerformancePayload = null;

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

function formatPlanLabel(planCode, isAdmin) {
  if (isAdmin) return "Admin";
  const safe = String(planCode || "free").toLowerCase();
  if (safe === "starter") return "Starter";
  if (safe === "pro") return "Pro";
  return "Free";
}

function syncUpgradeLinkForPlan(planCode, isAdmin) {
  const hangerEl = document.getElementById("billing-hanger");
  if (!upgradeLinkEl || !planPillEl || !hangerEl) return;

  const safe = String(planCode || "free").toLowerCase();
  const isPaid = safe === "starter" || safe === "pro" || isAdmin;
  planPillEl.textContent = isPaid ? (formatPlanLabel(planCode, isAdmin) + " Active") : "Unlock";

  if (isPaid) {
    hangerEl.hidden = true;
    return;
  }

  const returnPath = "/dashboard/?billing=pending";
  const targetPlan = safe === "free" ? "starter" : safe;
  upgradeLinkEl.href =
    "/buy/?plan=" + encodeURIComponent(targetPlan) + "&return=" + encodeURIComponent(returnPath);
  hangerEl.hidden = false;
}

async function loadAccountPlanAndBillingUi() {
  try {
    const account = await fetchAccountPlan();
    syncUpgradeLinkForPlan(account.plan_code, !!account.is_admin);
  } catch (error) {
    if (error.message === "AUTH_REQUIRED") {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
      redirectToLogin();
      return;
    }
    syncUpgradeLinkForPlan("free", false);
  }
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

function switchSidebarSection(sectionName) {
  const next = String(sectionName || "history").toLowerCase();
  const sectionMap = {
    history: sidebarHistorySectionEl,
    performance: sidebarPerformanceSectionEl,
    feedback: sidebarFeedbackSectionEl,
  };

  Object.entries(sectionMap).forEach(([key, section]) => {
    if (!section) return;
    section.hidden = key !== next;
  });

  sidebarNavEls.forEach((button) => {
    const isActive = button.getAttribute("data-section") === next;
    button.classList.toggle("active", isActive);
  });
}

function renderSidebarInsights() {
  if (!latestPerformancePayload) return;
  renderSidebarPerformance(sidebarPerformanceContentEl, latestPerformancePayload);
  renderSidebarActionFeedback(sidebarFeedbackContentEl, latestPerformancePayload);
}

function openSettingsModal() {
  if (!settingsModalEl) return;
  settingsModalEl.hidden = false;
}

function closeSettingsModal() {
  if (!settingsModalEl) return;
  settingsModalEl.hidden = true;
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

async function loadSevenDayPerformance() {
  try {
    const payload = await fetchUserPerformance(7);
    latestPerformancePayload = payload;
    renderSidebarInsights();
  } catch (error) {
    if (error.message === "AUTH_REQUIRED") {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
      redirectToLogin();
      return;
    }
    setStatus(error.message || "Failed to load 7-day performance.", true);
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
      await loadSevenDayPerformance();
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

if (sidebarFeedbackContentEl) {
  sidebarFeedbackContentEl.addEventListener("submit", async (event) => {
    const formEl = event.target;
    if (!(formEl instanceof HTMLFormElement)) return;
    if (formEl.id !== "action-feedback-form") return;
    event.preventDefault();

    const actionTaken = String(formEl.action_taken?.value || "").trim();
    const actionDate = String(formEl.action_date?.value || "").trim();
    const outcome = String(formEl.self_reported_outcome?.value || "").trim().toLowerCase();

    if (!actionTaken || !actionDate) {
      setStatus("Please provide action and date.", true);
      return;
    }

    const submitBtn = formEl.querySelector("#action-feedback-submit");
    if (submitBtn) submitBtn.disabled = true;

    setStatus("Saving action feedback...");
    try {
      await submitActionFeedback(actionTaken, actionDate, outcome);
      await loadSevenDayPerformance();
      setStatus("Action feedback saved. Impact will update as new runs come in.");
    } catch (error) {
      if (error.message === "AUTH_REQUIRED") {
        localStorage.removeItem(TOKEN_STORAGE_KEY);
        redirectToLogin();
        return;
      }
      setStatus(error.message || "Failed to save action feedback.", true);
    } finally {
      if (submitBtn) submitBtn.disabled = false;
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
      await loadSevenDayPerformance();
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

if (sidebarNavEls.length) {
  sidebarNavEls.forEach((button) => {
    button.addEventListener("click", () => {
      const target = button.getAttribute("data-section") || "history";
      switchSidebarSection(target);
    });
  });
}

if (userToggleBtn && userActionsEl) {
  userActionsEl.hidden = true;
  userToggleBtn.setAttribute("aria-expanded", "false");

  userToggleBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    const isOpen = !userActionsEl.hidden;
    userActionsEl.hidden = isOpen;
    userToggleBtn.setAttribute("aria-expanded", String(!isOpen));
  });

  document.addEventListener("click", (event) => {
    if (userActionsEl.hidden) return;
    if (sidebarUserEl && !sidebarUserEl.contains(event.target)) {
      userActionsEl.hidden = true;
      userToggleBtn.setAttribute("aria-expanded", "false");
    }
  });
}

if (openSettingsBtn) {
  openSettingsBtn.addEventListener("click", () => {
    if (userActionsEl) userActionsEl.hidden = true;
    if (userToggleBtn) userToggleBtn.setAttribute("aria-expanded", "false");
    openSettingsModal();
  });
}

if (settingsCloseBtn) {
  settingsCloseBtn.addEventListener("click", closeSettingsModal);
}

if (settingsModalEl) {
  settingsModalEl.addEventListener("click", (event) => {
    if (event.target === settingsModalEl) {
      closeSettingsModal();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeSettingsModal();
    }
  });
}

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

    switchSidebarSection("history");
    await loadSevenDayPerformance();
    await loadHistory();
    await loadShopifyStatus();
    await loadAccountPlanAndBillingUi();

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
  } catch (_error) {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    redirectToLogin();
  }
}

bootstrap();
