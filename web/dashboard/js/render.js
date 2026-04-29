function el(tag, className, html) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (html !== undefined) node.innerHTML = html;
  return node;
}

function textEl(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  node.textContent = text;
  return node;
}

function metric(label, value) {
  return el("article", "metric", `<span class="label">${label}</span><span class="value">${value}</span>`);
}

function decisionPill(label, value, tone = "") {
  return el(
    "article",
    `decision-pill${tone ? ` is-${tone}` : ""}`,
    `<span class="decision-pill-label">${label}</span><strong>${value}</strong>`
  );
}

function workspaceSection(title, subtitle) {
  const wrapper = el("article", "workspace-panel");
  wrapper.appendChild(textEl("p", "workspace-eyebrow", "Decision view"));
  wrapper.appendChild(textEl("h2", "workspace-heading", title));
  if (subtitle) wrapper.appendChild(textEl("p", "workspace-subtitle", subtitle));
  return wrapper;
}

function formatCurrency(value) {
  return `$${Number(value || 0).toLocaleString()}`;
}

function formatPct(value) {
  return `${Number(value || 0).toFixed(2)}%`;
}

function formatTrend(value, suffix = "%") {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "N/A";
  const numeric = Number(value);
  const sign = numeric > 0 ? "+" : "";
  return `${sign}${numeric.toFixed(2)}${suffix}`;
}

function formatShortDate(value) {
  if (!value) return "Unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function severityRank(severity) {
  const safe = String(severity || "").toLowerCase();
  if (safe === "critical") return 3;
  if (safe === "high") return 2;
  if (safe === "medium") return 1;
  return 0;
}

function actionFormMarkup(buttonLabel = "Save Action") {
  return `
    <label class="label">What action did you take?</label>
    <input name="action_taken" type="text" maxlength="500" required />
    <label class="label">When?</label>
    <input name="action_date" type="date" required />
    <label class="label">Did it help?</label>
    <select name="self_reported_outcome" required>
      <option value="yes">yes</option>
      <option value="no">no</option>
      <option value="unsure" selected>unsure</option>
    </select>
    <button class="action-feedback-submit" type="submit">${buttonLabel}</button>
  `;
}

function formatDayLabel(value) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  return date.toLocaleString(undefined, { month: "short", day: "numeric" });
}

function verticalTrendPlot(points, key, formatter) {
  const recent = Array.isArray(points) ? points.slice(-7) : [];
  const values = recent.map((point) => Number(point?.[key])).filter((value) => Number.isFinite(value));
  if (!values.length) return el("div", "trend-plot-empty", "No recent trend data");

  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(max - min, 0.0001);

  const bars = el("div", "trend-bars");
  recent.forEach((point) => {
    const raw = Number(point?.[key]);
    if (!Number.isFinite(raw)) {
      bars.appendChild(el("div", "trend-bar trend-bar-empty", `<span class="trend-bar-day">${formatDayLabel(point?.timestamp)}</span>`));
      return;
    }
    const ratio = span === 0 ? 1 : (raw - min) / span;
    const heightPct = Math.max(12, Math.round(ratio * 100));
    const formatted = formatter(raw);
    bars.appendChild(
      el(
        "div",
        "trend-bar",
        `<div class="trend-bar-fill" style="height:${heightPct}%;" title="${formatted} (${formatDayLabel(point?.timestamp)})"></div><span class="trend-bar-day">${formatDayLabel(point?.timestamp)}</span>`
      )
    );
  });
  return bars;
}

function trendCard(title, description, points, key, formatter) {
  const card = el("article", "narrative-card trend-card");
  card.appendChild(textEl("span", "narrative-kicker", title));
  card.appendChild(verticalTrendPlot(points, key, formatter));
  card.appendChild(textEl("p", "trend-description", description));
  return card;
}

export function renderUploadEvent(feed, fileName) {
  feed.appendChild(el("article", "feed-message user", `<p>Uploaded <strong>${fileName}</strong>. Run SignalOPs diagnosis.</p>`));
}

export function renderAnalysis(feed, payload) {
  if (!feed || !payload) return;
  const wrapper = el("article", "feed-message system");
  wrapper.appendChild(el("h3", "", "SignalOPs Analysis"));
  wrapper.appendChild(el("p", "", payload.summary || ""));
  feed.appendChild(wrapper);
}

export function renderRunsWorkspace(feed, { analysis, historyRows = [], uploadedFileName = "" } = {}) {
  if (!feed) return;
  feed.innerHTML = "";

  if (!analysis && (!Array.isArray(historyRows) || historyRows.length === 0)) {
    feed.appendChild(el("article", "feed-empty", "<h2>No runs yet</h2><p>Upload CSV or sync store to generate your first analysis.</p>"));
    return;
  }

  const wrapper = workspaceSection(
    "What happened during each analysis?",
    "Run outcome, top leak, and immediate next move."
  );

  if (uploadedFileName) {
    wrapper.appendChild(el("div", "workspace-banner", `<strong>Fresh input:</strong> ${uploadedFileName} was analyzed.`));
  }

  if (analysis) {
    const findings = Array.isArray(analysis.findings) ? analysis.findings : [];
    const topFinding = findings[0] || null;
    const criticalCount = findings.filter((item) => String(item.severity).toLowerCase() === "critical").length;
    const highCount = findings.filter((item) => String(item.severity).toLowerCase() === "high").length;

    const meta = el("div", "decision-pill-row");
    meta.appendChild(decisionPill("Run", analysis.run_id ? `#${analysis.run_id}` : "Latest"));
    meta.appendChild(decisionPill("Created", formatShortDate(analysis.created_at)));
    meta.appendChild(decisionPill("Source", analysis.source_file || "Unknown"));
    wrapper.appendChild(meta);

    const outcome = el("div", "run-signal-grid");
    outcome.appendChild(decisionPill("Findings", findings.length ? `${findings.length} active` : "Clear", findings.length ? "bad" : "good"));
    outcome.appendChild(decisionPill("Critical / High", `${criticalCount} / ${highCount}`, criticalCount || highCount ? "bad" : "neutral"));
    outcome.appendChild(decisionPill("Top leak", topFinding ? String(topFinding.title || "Leak detected") : "None", topFinding ? "bad" : "good"));
    wrapper.appendChild(outcome);

    const nextMove = el("section", "primary-decision-card");
    nextMove.appendChild(textEl("span", "narrative-kicker", "Next move"));
    nextMove.appendChild(
      textEl(
        "p",
        "primary-decision-text",
        topFinding
          ? (topFinding.what_to_do || topFinding.what_changed || "Assign owner and execute this week.")
          : "No urgent leak from this run. Keep monitoring on new data."
      )
    );
    wrapper.appendChild(nextMove);
  }

  feed.appendChild(wrapper);
}

export function renderStoreWorkspace(feed, { performance, analysis } = {}) {
  if (!feed) return;
  feed.innerHTML = "";

  const summary = performance?.summary || {};
  const points = Array.isArray(performance?.points) ? performance.points : [];
  const fallbackPoint = analysis?.features
    ? {
        timestamp: analysis.created_at || new Date().toISOString(),
        total_revenue: Number(analysis.features.total_revenue || 0),
        repeat_rate: Number(analysis.features.repeat_rate || 0),
        refund_rate: Number(analysis.features.refund_rate || 0),
      }
    : null;
  const plotPoints = points.length ? points : (fallbackPoint ? [fallbackPoint] : []);

  const wrapper = workspaceSection(
    "What changed?",
    "Revenue momentum, retention, and refund movement for this window."
  );

  const top = el("div", "metrics-grid workspace-metrics");
  top.appendChild(metric("WoW Revenue", summary.week_over_week_revenue_change_pct == null ? "N/A" : formatPct(summary.week_over_week_revenue_change_pct)));
  top.appendChild(metric("Repeat Rate", formatPct(summary.repeat_rate || 0)));
  top.appendChild(metric("Refund Rate", formatPct(summary.refund_rate || 0)));
  wrapper.appendChild(top);

  const trends = el("div", "narrative-grid");
  trends.appendChild(
    trendCard(
      "Demand momentum",
      summary.week_over_week_revenue_change_pct == null
        ? "Trend unavailable yet."
        : `WoW revenue is ${formatTrend(summary.week_over_week_revenue_change_pct)}.`,
      plotPoints,
      "total_revenue",
      (value) => formatCurrency(value)
    )
  );
  trends.appendChild(
    trendCard(
      "Retention strength",
      `Repeat rate is ${formatPct(summary.repeat_rate || 0)}.`,
      plotPoints,
      "repeat_rate",
      (value) => formatPct(value)
    )
  );
  trends.appendChild(
    trendCard(
      "Refund pressure",
      `Refund rate is ${formatPct(summary.refund_rate || 0)}.`,
      plotPoints,
      "refund_rate",
      (value) => formatPct(value)
    )
  );
  wrapper.appendChild(trends);

  const brief = el("section", "primary-decision-card");
  brief.appendChild(textEl("span", "narrative-kicker", "Interpretation"));
  brief.appendChild(
    textEl(
      "p",
      "primary-decision-text",
      `WoW ${summary.week_over_week_revenue_change_pct == null ? "N/A" : formatTrend(summary.week_over_week_revenue_change_pct)}, repeat ${formatPct(summary.repeat_rate || 0)}, refund ${formatPct(summary.refund_rate || 0)}.`
    )
  );
  wrapper.appendChild(brief);

  feed.appendChild(wrapper);
}

export function renderActionWorkspace(feed, { performance, analysis } = {}) {
  if (!feed) return;
  feed.innerHTML = "";

  const wrapper = workspaceSection(
    "What should I do now?",
    "One active leak with a focused 7-day playbook."
  );

  const findings = Array.isArray(analysis?.findings) ? analysis.findings : [];
  const feedback = performance?.action_feedback || null;

  if (findings.length) {
    const activeLeak = [...findings].sort((a, b) => severityRank(b.severity) - severityRank(a.severity))[0];
    wrapper.appendChild(
      el(
        "article",
        "action-card",
        `<div class="action-card-head"><span class="action-priority">Active leak</span><span class="severity">${activeLeak.severity}</span></div><h3>${activeLeak.title}</h3><p class="action-change">${activeLeak.what_changed || ""}</p>`
      )
    );

    const playbook = el("div", "action-list");
    playbook.appendChild(el("article", "action-card", `<h3>Step 1 (Today)</h3><p class="action-step">${activeLeak.what_to_do || "Assign owner and start remediation."}</p>`));
    playbook.appendChild(el("article", "action-card", "<h3>Step 2 (48 hours)</h3><p class=\"action-step\">Check execution and clear blockers.</p>"));
    playbook.appendChild(el("article", "action-card", "<h3>Step 3 (Day 7)</h3><p class=\"action-step\">Review metric movement and decide next action.</p>"));
    wrapper.appendChild(playbook);
  } else {
    wrapper.appendChild(el("article", "narrative-card is-good", "<span class=\"narrative-kicker\">No urgent leak</span><p>No active leak crossed thresholds. Continue monitoring this week.</p>"));
  }

  const feedbackPanel = el("section", "feedback-panel action-workspace-panel");
  feedbackPanel.appendChild(textEl("h3", "workspace-subheading", "Execution log"));
  if (feedback) {
    feedbackPanel.appendChild(
      el(
        "p",
        "feedback-inline-meta",
        `<strong>Action:</strong> ${feedback.action_taken}<br><strong>Date:</strong> ${feedback.action_date}<br><strong>Status:</strong> ${feedback.self_reported_outcome}<br><strong>Impact:</strong> <span class="impact-chip">${feedback.impact_label || "Pending"}</span>`
      )
    );
  } else {
    feedbackPanel.appendChild(textEl("p", "sidebar-note", "No execution log yet. Save what was done to track impact."));
  }

  const form = el("form", "action-feedback-form workspace-action-form", actionFormMarkup("Save Action"));
  form.setAttribute("data-action-feedback-form", "true");
  feedbackPanel.appendChild(form);
  wrapper.appendChild(feedbackPanel);

  feed.appendChild(wrapper);
}

export function renderSidebarPerformance(container, payload, analysis = null, shopifyStatus = null) {
  if (!container) return;
  const summary = payload?.summary || {};
  const points = Array.isArray(payload?.points) ? payload.points.length : 0;
  const findings = Array.isArray(analysis?.findings) ? analysis.findings.length : 0;
  container.innerHTML = "";
  const list = el("dl", "sidebar-kv-list");
  list.appendChild(el("div", "sidebar-kv-item", `<dt>WoW</dt><dd>${summary.week_over_week_revenue_change_pct == null ? "N/A" : formatPct(summary.week_over_week_revenue_change_pct)}</dd>`));
  list.appendChild(el("div", "sidebar-kv-item", `<dt>Repeat</dt><dd>${formatPct(summary.repeat_rate || 0)}</dd>`));
  list.appendChild(el("div", "sidebar-kv-item", `<dt>Refund</dt><dd>${formatPct(summary.refund_rate || 0)}</dd>`));
  container.appendChild(list);
  container.appendChild(el("p", "sidebar-note", `${points} run${points === 1 ? "" : "s"} in current window. ${findings} active leak${findings === 1 ? "" : "s"}.`));
  container.appendChild(el("p", "sidebar-note", shopifyStatus?.connected ? `Connected: ${shopifyStatus.shop_domain || "Shopify"}.` : "Shopify not connected yet."));
}

export function renderSidebarActionFeedback(container, payload, analysis = null) {
  if (!container) return;
  container.innerHTML = "";
}

export function clearEmptyState(feed, empty) {
  if (empty && feed.contains(empty)) feed.removeChild(empty);
}

export function resetFeed(feed) {
  if (!feed) return;
  feed.innerHTML = "";
}

export function renderHistoryList(historyListEl, rows, onClick, activeRunId = null) {
  if (!historyListEl) return;
  historyListEl.innerHTML = "";
  if (!Array.isArray(rows) || rows.length === 0) {
    historyListEl.innerHTML = '<li class="history-empty">No saved analyses yet.</li>';
    return;
  }
  rows.forEach((row) => {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = `history-item${activeRunId === row.run_id ? " active" : ""}`;
    button.innerHTML = `<strong>#${row.run_id} ${row.source_file}</strong><span>${formatShortDate(row.created_at)}</span>`;
    button.addEventListener("click", () => onClick(row.run_id));
    item.appendChild(button);
    historyListEl.appendChild(item);
  });
}
