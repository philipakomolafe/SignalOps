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
  sendWeeklyReportNow,
  startShopifyConnect,
  submitActionFeedback,
} from "./api.js";
import { TOKEN_STORAGE_KEY } from "./config.js";
import {
  renderHistoryList,
  renderRunsWorkspace,
  renderStoreWorkspace,
  renderActionWorkspace,
  renderSidebarActionFeedback,
  renderSidebarPerformance,
  renderUploadEvent,
} from "./render.js";

const feed = document.getElementById("analysis-feed");
const form = document.getElementById("upload-form");
const fileInput = document.getElementById("csv-file");
const dropZone = document.getElementById("drop-zone");
const statusEl = document.getElementById("status");
const historyListEl = document.getElementById("history-list");
const runButton = form ? form.querySelector("button[type='submit']") : null;
const userNameEl = document.getElementById("user-name");
const userPopoverNameEl = document.getElementById("user-popover-name");
const userToggleBtn = document.getElementById("user-toggle");
const userActionsEl = document.getElementById("user-actions");
const sidebarUserEl = document.querySelector(".sidebar-user");
const logoutBtn = document.getElementById("logout-btn");
const upgradePlanBtn = document.getElementById("upgrade-plan-btn");

const shopDomainInputEl = document.getElementById("shop-domain-input");
const shopifyConnectBtn = document.getElementById("shopify-connect-btn");
const shopifyDisconnectBtn = document.getElementById("shopify-disconnect-btn");
const shopifySyncBtn = document.getElementById("shopify-sync-btn");
const weeklyReportBtn = document.getElementById("weekly-report-btn");
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
const settingsNavItems = Array.from(document.querySelectorAll(".settings-nav-item"));
const workspaceHeadingEl = document.querySelector(".workspace-title h1");
const workspaceSubtitleEl = document.querySelector(".workspace-title p");

let currentRunId = null;
let latestPerformancePayload = null;
let latestHistoryRows = [];
let activeAnalysisPayload = null;
let latestShopifyStatus = null;
let currentSection = "history";
let lastUploadedFileName = "";
let currentPlanCode = "free";

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
  currentPlanCode = safe;
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

function buildUpgradeCheckoutUrl() {
  const safe = String(currentPlanCode || "free").toLowerCase();
  const targetPlan = safe === "free" ? "starter" : "pro";
  const returnPath = "/dashboard/?billing=pending";
  return "/buy/?plan=" + encodeURIComponent(targetPlan) + "&return=" + encodeURIComponent(returnPath);
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
  [shopifyConnectBtn, shopifyDisconnectBtn, shopifySyncBtn, weeklyReportBtn].forEach((button) => {
    if (button) button.disabled = disabled;
  });
}

function switchSidebarSection(sectionName) {
  const next = String(sectionName || "history").toLowerCase();
  currentSection = next;
  const sectionMap = {
    history: sidebarHistorySectionEl,
    performance: sidebarPerformanceSectionEl,
    feedback: null,
  };

  Object.entries(sectionMap).forEach(([key, section]) => {
    if (!section) return;
    section.hidden = key !== next;
  });

  if (sidebarFeedbackSectionEl) {
    sidebarFeedbackSectionEl.hidden = true;
  }

  sidebarNavEls.forEach((button) => {
    const isActive = button.getAttribute("data-section") === next;
    button.classList.toggle("active", isActive);
  });

  updateWorkspaceHeader(next);
  renderWorkspaceSection();
}

function renderSidebarInsights() {
  if (!latestPerformancePayload) return;
  renderSidebarPerformance(
    sidebarPerformanceContentEl,
    latestPerformancePayload,
    activeAnalysisPayload,
    latestShopifyStatus
  );
  renderSidebarActionFeedback(
    sidebarFeedbackContentEl,
    latestPerformancePayload,
    activeAnalysisPayload
  );
}

function updateWorkspaceHeader(sectionName) {
  if (!workspaceHeadingEl || !workspaceSubtitleEl) return;

  if (sectionName === "performance") {
    workspaceHeadingEl.textContent = "Store Workspace";
    workspaceSubtitleEl.textContent = "Track momentum, retention, refunds, and monitoring state in one operating view.";
    return;
  }

  if (sectionName === "feedback") {
    workspaceHeadingEl.textContent = "Action Workspace";
    workspaceSubtitleEl.textContent = "Turn leak signals into deliberate actions, then record and assess the impact.";
    return;
  }

  workspaceHeadingEl.textContent = "Analysis Workspace";
  workspaceSubtitleEl.textContent = "Open the latest run, inspect the leak brief, and compare recent analysis activity.";
}

function renderWorkspaceSection() {
  if (!feed) return;

  if (currentSection === "performance") {
    renderStoreWorkspace(feed, {
      performance: latestPerformancePayload,
      analysis: activeAnalysisPayload,
      shopifyStatus: latestShopifyStatus,
    });
    return;
  }

  if (currentSection === "feedback") {
    renderActionWorkspace(feed, {
      performance: latestPerformancePayload,
      analysis: activeAnalysisPayload,
    });
    return;
  }

  renderRunsWorkspace(feed, {
    analysis: activeAnalysisPayload,
    historyRows: latestHistoryRows,
    uploadedFileName: lastUploadedFileName,
  });
}

function openSettingsModal() {
  if (!settingsModalEl) return;
  settingsModalEl.hidden = false;
  switchSettingsTab("integrations");
}

function closeSettingsModal() {
  if (!settingsModalEl) return;
  settingsModalEl.hidden = true;
}

function switchSettingsTab(tabName) {
  const next = String(tabName || "integrations").toLowerCase();
  settingsNavItems.forEach((button) => {
    const tab = String(button.getAttribute("data-settings-tab") || "").toLowerCase();
    button.classList.toggle("active", tab === next);
  });

  const paneIds = ["general", "integrations", "notifications"];
  paneIds.forEach((name) => {
    const pane = document.getElementById(`settings-pane-${name}`);
    if (!pane) return;
    pane.hidden = name !== next;
  });
}

async function loadShopifyStatus() {
  try {
    const status = await fetchShopifyStatus();
    latestShopifyStatus = status;
    if (!status.connected) {
      setShopifyStatus("No Shopify connection yet.");
      renderSidebarInsights();
      renderWorkspaceSection();
      return;
    }

    if (shopDomainInputEl && status.shop_domain) {
      shopDomainInputEl.value = status.shop_domain;
    }

    const synced = status.last_synced_at ? ` Last sync: ${status.last_synced_at}.` : "";
    setShopifyStatus(`Connected: ${status.shop_domain || "store"}.${synced}`);
    renderSidebarInsights();
    renderWorkspaceSection();
  } catch (error) {
    if (error.message === "AUTH_REQUIRED") {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
      redirectToLogin();
      return;
    }
    latestShopifyStatus = null;
    setShopifyStatus(error.message || "Failed to fetch Shopify status.", true);
  }
}

function showSingleAnalysis(payload, fileName = null) {
  activeAnalysisPayload = payload;
  lastUploadedFileName = fileName || "";
  renderWorkspaceSection();
  if (currentSection === "history" && feed) {
    feed.scrollTop = 0;
  }
  currentRunId = payload?.run_id ?? null;
  renderHistoryList(historyListEl, latestHistoryRows, handleHistoryRunOpen, currentRunId);
  renderSidebarInsights();
  if (currentRunId) {
    updateConversationUrl(currentRunId);
  }
}

async function loadSevenDayPerformance() {
  try {
    const payload = await fetchUserPerformance(7);
    latestPerformancePayload = payload;
    renderSidebarInsights();
    renderWorkspaceSection();
  } catch (error) {
    if (error.message === "AUTH_REQUIRED") {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
      redirectToLogin();
      return;
    }
    setStatus(error.message || "Failed to load 7-day performance.", true);
  }
}

async function handleHistoryRunOpen(runId) {
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
}

async function loadHistory() {
  try {
    const rows = await fetchAnalysisHistory(20);
    latestHistoryRows = Array.isArray(rows) ? rows : [];
    renderHistoryList(historyListEl, latestHistoryRows, handleHistoryRunOpen, currentRunId);
    renderWorkspaceSection();
    return latestHistoryRows;
  } catch (error) {
    if (error.message === "AUTH_REQUIRED") {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
      redirectToLogin();
      return;
    }
    latestHistoryRows = [];
    renderHistoryList(historyListEl, latestHistoryRows, handleHistoryRunOpen, currentRunId);
    renderWorkspaceSection();
    setStatus(error.message || "Failed to load history.", true);
    return [];
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
    activeAnalysisPayload = null;
    lastUploadedFileName = file.name;
    renderWorkspaceSection();
    if (currentSection === "history") {
      renderUploadEvent(feed, file.name);
    }
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

document.addEventListener("submit", async (event) => {
  const formEl = event.target;
  if (!(formEl instanceof HTMLFormElement)) return;
  if (!formEl.matches("[data-action-feedback-form='true']")) return;
  event.preventDefault();

  const formData = new FormData(formEl);
  const actionTaken = String(formData.get("action_taken") || "").trim();
  const actionDate = String(formData.get("action_date") || "").trim();
  const outcome = String(formData.get("self_reported_outcome") || "").trim().toLowerCase();

  if (!actionTaken || !actionDate) {
    setStatus("Please provide action and date.", true);
    return;
  }

  const submitBtn = formEl.querySelector(".action-feedback-submit");
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

document.addEventListener("click", (event) => {
  const trigger = event.target instanceof Element
    ? event.target.closest(".playbook-activate-btn")
    : null;
  if (!trigger) return;

  const actionText = String(trigger.getAttribute("data-playbook-action") || "").trim();
  if (!actionText) return;

  const targetForm = document.querySelector("[data-action-feedback-form='true']");
  if (!(targetForm instanceof HTMLFormElement)) {
    setStatus("Open Action workspace to activate this playbook.", true);
    return;
  }

  const actionInput = targetForm.querySelector("input[name='action_taken']");
  const dateInput = targetForm.querySelector("input[name='action_date']");
  const outcomeInput = targetForm.querySelector("select[name='self_reported_outcome']");

  if (actionInput instanceof HTMLInputElement) {
    actionInput.value = actionText;
  }
  if (dateInput instanceof HTMLInputElement && !dateInput.value) {
    const now = new Date();
    const month = String(now.getMonth() + 1).padStart(2, "0");
    const day = String(now.getDate()).padStart(2, "0");
    dateInput.value = `${now.getFullYear()}-${month}-${day}`;
  }
  if (outcomeInput instanceof HTMLSelectElement) {
    outcomeInput.value = "unsure";
  }

  targetForm.scrollIntoView({ behavior: "smooth", block: "center" });
  setStatus("Playbook activated. Confirm and save this action below.");
});

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

if (upgradePlanBtn) {
  upgradePlanBtn.addEventListener("click", () => {
    if (userActionsEl) userActionsEl.hidden = true;
    if (userToggleBtn) userToggleBtn.setAttribute("aria-expanded", "false");
    window.location.href = buildUpgradeCheckoutUrl();
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
      const rows = await loadHistory();
      await loadShopifyStatus();
      await loadSevenDayPerformance();
      if (result.triggered_analyses > 0 && Array.isArray(rows) && rows.length) {
        const latestRunId = rows[0]?.run_id;
        if (latestRunId && latestRunId !== currentRunId) {
          const payload = await fetchAnalysisById(latestRunId);
          showSingleAnalysis(payload);
          switchSidebarSection("history");
          setStatus(`Monitor complete. Opened latest run #${latestRunId}.`);
        }
      }
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

if (weeklyReportBtn) {
  weeklyReportBtn.addEventListener("click", async () => {
    setShopifyButtonsDisabled(true);
    setShopifyStatus("Sending weekly report...");
    try {
      const result = await sendWeeklyReportNow();
      setShopifyStatus(`Weekly report sent to ${result.recipient}.`);
      setStatus(`Weekly report sent to ${result.recipient}.`);
    } catch (error) {
      if (error.message === "AUTH_REQUIRED") {
        localStorage.removeItem(TOKEN_STORAGE_KEY);
        redirectToLogin();
        return;
      }
      setShopifyStatus(error.message || "Failed to send weekly report.", true);
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
      if (target === "history") setStatus("Showing recent analysis runs.");
      if (target === "performance") setStatus("Showing 7-day store performance.");
      if (target === "feedback") setStatus("Showing action feedback.");
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

if (settingsNavItems.length) {
  settingsNavItems.forEach((button) => {
    button.addEventListener("click", () => {
      const tab = button.getAttribute("data-settings-tab") || "integrations";
      switchSettingsTab(tab);
    });
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
      const displayName = me.full_name || fallbackName;
      userNameEl.textContent = displayName;
      if (userPopoverNameEl) userPopoverNameEl.textContent = displayName;
    }

    updateWorkspaceHeader("history");
    await loadSevenDayPerformance();
    const rows = await loadHistory();
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
    } else if ((!activeAnalysisPayload || !currentRunId) && Array.isArray(rows) && rows.length) {
      try {
        const payload = await fetchAnalysisById(rows[0].run_id);
        showSingleAnalysis(payload);
      } catch (_error) {
        renderWorkspaceSection();
      }
    } else {
      renderWorkspaceSection();
    }
  } catch (_error) {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    redirectToLogin();
  }
}

bootstrap();
