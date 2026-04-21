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

function diagnosis(label, body) {
  return el("article", "diagnosis", `<span class="label">${label}</span><p>${body}</p>`);
}

function formatCurrency(value) {
  return `$${Number(value || 0).toLocaleString()}`;
}

function formatPct(value) {
  return `${Number(value || 0).toFixed(2)}%`;
}

function formatShortDate(value) {
  if (!value) return "Unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function severityRank(severity) {
  const safe = String(severity || "").toLowerCase();
  if (safe === "critical") return 3;
  if (safe === "high") return 2;
  if (safe === "medium") return 1;
  return 0;
}

function formatTrend(value, suffix = "%") {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "N/A";
  }
  const numeric = Number(value);
  const sign = numeric > 0 ? "+" : "";
  return `${sign}${numeric.toFixed(2)}${suffix}`;
}

function healthTone(value, { goodMin = null, badMin = null, reverse = false } = {}) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "neutral";
  }

  const numeric = Number(value);
  if (reverse) {
    if (goodMin !== null && numeric <= goodMin) return "good";
    if (badMin !== null && numeric >= badMin) return "bad";
    return "neutral";
  }

  if (goodMin !== null && numeric >= goodMin) return "good";
  if (badMin !== null && numeric <= badMin) return "bad";
  return "neutral";
}

function workspaceSection(title, subtitle) {
  const wrapper = el("article", "workspace-panel");
  wrapper.appendChild(textEl("p", "workspace-eyebrow", "Decision view"));
  wrapper.appendChild(textEl("h2", "workspace-heading", title));
  if (subtitle) {
    wrapper.appendChild(textEl("p", "workspace-subtitle", subtitle));
  }
  return wrapper;
}

function narrativeCard(title, body, tone = "") {
  return el(
    "article",
    `narrative-card${tone ? ` is-${tone}` : ""}`,
    `<span class="narrative-kicker">${title}</span><p>${body}</p>`
  );
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

function appendTopFindingCards(container, findings) {
  const sorted = [...(Array.isArray(findings) ? findings : [])].sort(
    (left, right) => severityRank(right.severity) - severityRank(left.severity)
  );

  const cards = el("div", "narrative-grid");
  if (!sorted.length) {
    cards.appendChild(
      narrativeCard(
        "Stable",
        "No critical leak triggered in the latest run. Keep watching repeat rate, refund rate, and revenue momentum weekly.",
        "good"
      )
    );
    container.appendChild(cards);
    return;
  }

  sorted.slice(0, 3).forEach((finding) => {
    cards.appendChild(
      el(
        "article",
        `finding-brief severity-${String(finding.severity || "medium").toLowerCase()}`,
        `
          <div class="finding-brief-head">
            <span class="severity">${finding.severity}</span>
            <h3>${finding.title}</h3>
          </div>
          <p>${finding.what_changed || finding.likely_why || ""}</p>
          <div class="finding-brief-action">${finding.what_to_do || ""}</div>
        `
      )
    );
  });

  container.appendChild(cards);
}

function productRow(item, emphasisLabel, emphasisValue) {
  const label = item.title || item.sku || item.product_id || item.variant_id || "Untitled product";
  return el(
    "article",
    "product-row",
    `
      <div class="product-row-head">
        <strong>${label}</strong>
        <span>${emphasisLabel}: ${emphasisValue}</span>
      </div>
      <div class="product-row-meta">
        <span>Units ${Number(item.units_sold || 0).toLocaleString()}</span>
        <span>Orders ${Number(item.order_count || 0).toLocaleString()}</span>
        <span>Refunds ${formatCurrency(item.refund_amount || 0)}</span>
      </div>
    `
  );
}

function renderProductPerformance(features) {
  const productPerformance = features.product_performance || {};
  const topRevenue = Array.isArray(productPerformance.top_products_by_revenue)
    ? productPerformance.top_products_by_revenue
    : [];
  const topRefund = Array.isArray(productPerformance.top_products_by_refund_rate)
    ? productPerformance.top_products_by_refund_rate
    : [];

  if (!productPerformance.products_analyzed && topRevenue.length === 0 && topRefund.length === 0) {
    return null;
  }

  const disclosureEl = disclosure(
    "Product performance",
    `${Number(productPerformance.products_analyzed || 0).toLocaleString()} products analyzed`
  );

  const overview = el("div", "product-overview");
  overview.appendChild(metric("Products", Number(productPerformance.products_analyzed || 0).toLocaleString()));
  overview.appendChild(metric("Units Sold", Number(productPerformance.units_sold || 0).toLocaleString()));
  disclosureEl.appendChild(overview);

  const sections = el("div", "product-sections");

  if (topRevenue.length) {
    const revenueSection = el("section", "product-section");
    revenueSection.appendChild(el("h4", "", "Top by revenue"));
    const revenueList = el("div", "product-list");
    topRevenue.forEach((item) => {
      revenueList.appendChild(productRow(item, "Net", formatCurrency(item.net_revenue || 0)));
    });
    revenueSection.appendChild(revenueList);
    sections.appendChild(revenueSection);
  }

  if (topRefund.length) {
    const refundSection = el("section", "product-section");
    refundSection.appendChild(el("h4", "", "Top by refund rate"));
    const refundList = el("div", "product-list");
    topRefund.forEach((item) => {
      refundList.appendChild(productRow(item, "Refund rate", formatPct(item.refund_rate || 0)));
    });
    refundSection.appendChild(refundList);
    sections.appendChild(refundSection);
  }

  disclosureEl.appendChild(sections);
  return disclosureEl;
}

function disclosure(title, subtitle = "") {
  const details = el("details", "disclosure");
  const summary = el("summary", "");
  summary.appendChild(el("span", "disclosure-title", title));
  if (subtitle) {
    summary.appendChild(el("span", "disclosure-subtitle", subtitle));
  }
  details.appendChild(summary);
  return details;
}

export function renderUploadEvent(feed, fileName) {
  const msg = el("article", "feed-message user", `<p>Uploaded <strong>${fileName}</strong>. Run SignalOPs diagnosis.</p>`);
  feed.appendChild(msg);
}

export function renderAnalysis(feed, payload) {
  const wrapper = el("article", "feed-message system");

  wrapper.appendChild(el("h3", "", "SignalOPs Analysis"));
  wrapper.appendChild(el("p", "", payload.summary || ""));
  if (payload.run_id || payload.created_at || payload.source_file) {
    const metaText = [
      payload.run_id ? `Run #${payload.run_id}` : null,
      payload.created_at ? payload.created_at : null,
      payload.source_file ? payload.source_file : null,
    ].filter(Boolean).join(" | ");
    wrapper.appendChild(el("p", "", metaText));
  }

  const diagnosisGrid = el("div", "diagnosis-grid");
  diagnosisGrid.appendChild(diagnosis("What Changed", payload.diagnosis?.what_changed || "N/A"));
  diagnosisGrid.appendChild(diagnosis("Likely Why", payload.diagnosis?.likely_why || "N/A"));
  diagnosisGrid.appendChild(diagnosis("What To Do", payload.diagnosis?.what_to_do || "N/A"));
  diagnosisGrid.appendChild(diagnosis("What To Watch Next", payload.diagnosis?.what_to_watch_next || "N/A"));
  const diagnosisDisclosure = disclosure("Detailed diagnosis", "Expand for full narrative");
  diagnosisDisclosure.appendChild(diagnosisGrid);
  wrapper.appendChild(diagnosisDisclosure);

  const features = payload.features || {};
  const metricsGrid = el("div", "metrics-grid");
  metricsGrid.appendChild(metric("Total Revenue", formatCurrency(features.total_revenue || 0)));
  metricsGrid.appendChild(metric("Revenue/User", formatCurrency(features.revenue_per_user || 0)));
  metricsGrid.appendChild(metric("Purchase Frequency", Number(features.purchase_frequency || 0).toFixed(2)));
  metricsGrid.appendChild(metric("Repeat Rate", formatPct(features.repeat_rate || 0)));
  metricsGrid.appendChild(metric("Refund Rate", formatPct(features.refund_rate || 0)));
  metricsGrid.appendChild(metric(
    "WoW Revenue",
    features.week_over_week_revenue_change_pct === null || features.week_over_week_revenue_change_pct === undefined
      ? "N/A"
      : formatPct(features.week_over_week_revenue_change_pct)
  ));
  wrapper.appendChild(metricsGrid);

  const productPerformance = renderProductPerformance(features);
  if (productPerformance) {
    wrapper.appendChild(productPerformance);
  }

  const findingsGrid = el("div", "findings-grid");
  const findings = Array.isArray(payload.findings) ? payload.findings : [];
  if (findings.length === 0) {
    findingsGrid.appendChild(el("article", "finding", `<span class="severity">Stable</span><p>No critical leaks detected by current rules.</p>`));
  } else {
    findings.forEach((finding) => {
      findingsGrid.appendChild(
        el(
          "article",
          "finding",
          `<span class="severity">${finding.severity}</span><h4>${finding.title}</h4><p>${finding.what_changed}</p>`
        )
      );
    });
  }

  const findingsDisclosure = disclosure(
    "Leak findings",
    findings.length ? `${findings.length} item${findings.length === 1 ? "" : "s"}` : "No critical leaks"
  );
  findingsDisclosure.appendChild(findingsGrid);
  wrapper.appendChild(findingsDisclosure);

  feed.appendChild(wrapper);
}

export function renderRunsWorkspace(feed, { analysis, historyRows = [], uploadedFileName = "" } = {}) {
  if (!feed) return;
  feed.innerHTML = "";

  if (!analysis && (!Array.isArray(historyRows) || historyRows.length === 0)) {
    feed.appendChild(
      el(
        "article",
        "feed-empty",
        "<h2>No runs yet</h2><p>Upload a Shopify orders CSV or connect a store to generate your first leak brief.</p>"
      )
    );
    return;
  }

  const wrapper = workspaceSection(
    "Latest leak brief",
    "Open the latest run first. This is the fastest way to see what changed and what to fix next."
  );

  if (uploadedFileName) {
    wrapper.appendChild(
      el(
        "div",
        "workspace-banner",
        `<strong>Fresh input:</strong> ${uploadedFileName} was just analyzed.`
      )
    );
  }

  if (analysis) {
    const findings = Array.isArray(analysis.findings) ? analysis.findings : [];
    const criticalCount = findings.filter((item) => String(item.severity).toLowerCase() === "critical").length;
    const highCount = findings.filter((item) => String(item.severity).toLowerCase() === "high").length;

    const grid = el("div", "metrics-grid workspace-metrics");
    grid.appendChild(metric("Run", analysis.run_id ? `#${analysis.run_id}` : "Latest"));
    grid.appendChild(metric("Findings", String(findings.length)));
    grid.appendChild(metric("Critical / High", `${criticalCount} / ${highCount}`));
    grid.appendChild(metric("Source", analysis.source_file || "Unknown"));
    grid.appendChild(metric("Created", formatShortDate(analysis.created_at)));
    grid.appendChild(metric("Segment", analysis.segment || "Shopify"));
    wrapper.appendChild(grid);

    wrapper.appendChild(
      narrativeCard(
        "Run summary",
        analysis.summary || "No summary available for this run.",
        findings.length ? "bad" : "good"
      )
    );

    appendTopFindingCards(wrapper, findings);
  } else {
    wrapper.appendChild(
      narrativeCard(
        "No run opened",
        "Recent run history is available in the sidebar. Open one to see the full leak diagnosis.",
        "neutral"
      )
    );
  }

  feed.appendChild(wrapper);

  if (analysis) {
    renderAnalysis(feed, analysis);
  }
}

export function renderStoreWorkspace(feed, { performance, analysis, shopifyStatus } = {}) {
  if (!feed) return;
  feed.innerHTML = "";

  const summary = performance && performance.summary ? performance.summary : {};
  const points = Array.isArray(performance && performance.points) ? performance.points : [];
  const findings = Array.isArray(analysis && analysis.findings) ? analysis.findings : [];

  const wrapper = workspaceSection(
    "Store operating view",
    "This section keeps the entire store in view: momentum, retention, refund pressure, and current monitoring state."
  );

  const metricsGrid = el("div", "metrics-grid workspace-metrics");
  metricsGrid.appendChild(metric("Revenue", formatCurrency(summary.total_revenue || 0)));
  metricsGrid.appendChild(metric("Orders", Number(summary.order_count || 0).toLocaleString()));
  metricsGrid.appendChild(metric("Customers", Number(summary.customer_count || 0).toLocaleString()));
  metricsGrid.appendChild(metric("Revenue/User", formatCurrency(summary.revenue_per_user || 0)));
  metricsGrid.appendChild(metric("Repeat Rate", formatPct(summary.repeat_rate || 0)));
  metricsGrid.appendChild(
    metric(
      "WoW Revenue",
      summary.week_over_week_revenue_change_pct === null || summary.week_over_week_revenue_change_pct === undefined
        ? "N/A"
        : formatPct(summary.week_over_week_revenue_change_pct)
    )
  );
  wrapper.appendChild(metricsGrid);

  const narrativeGrid = el("div", "narrative-grid");
  narrativeGrid.appendChild(
    narrativeCard(
      "Demand momentum",
      summary.week_over_week_revenue_change_pct === null || summary.week_over_week_revenue_change_pct === undefined
        ? "Revenue trend is not available yet because there is not enough recent run history."
        : `Week-over-week revenue is ${formatTrend(summary.week_over_week_revenue_change_pct)}. Treat this as the top store-level demand signal.`,
      healthTone(summary.week_over_week_revenue_change_pct, { goodMin: 0, badMin: -10 })
    )
  );
  narrativeGrid.appendChild(
    narrativeCard(
      "Retention strength",
      `Repeat rate is ${formatPct(summary.repeat_rate || 0)} and purchase frequency is ${Number(summary.purchase_frequency || 0).toFixed(2)}.`,
      healthTone(summary.repeat_rate, { goodMin: 20, badMin: 10 })
    )
  );
  narrativeGrid.appendChild(
    narrativeCard(
      "Refund pressure",
      `Refund rate is ${formatPct(summary.refund_rate || 0)} across the last ${performance?.window_days || 7} days.`,
      healthTone(summary.refund_rate, { goodMin: 4, badMin: 8, reverse: true })
    )
  );
  wrapper.appendChild(narrativeGrid);

  const monitorGrid = el("div", "monitor-grid");
  monitorGrid.appendChild(
    el(
      "article",
      "monitor-card",
      `<span class="label">Analysis coverage</span><strong>${points.length} run${points.length === 1 ? "" : "s"}</strong><p>Combined view across the last ${performance?.window_days || 7} days.</p>`
    )
  );
  monitorGrid.appendChild(
    el(
      "article",
      "monitor-card",
      `<span class="label">Shopify connection</span><strong>${
        shopifyStatus?.connected ? "Connected" : "Not connected"
      }</strong><p>${
        shopifyStatus?.connected
          ? `${shopifyStatus.shop_domain || "Store"}${shopifyStatus.last_synced_at ? ` • last sync ${formatShortDate(shopifyStatus.last_synced_at)}` : ""}`
          : "Connect Shopify to move from manual CSV uploads to continuous monitoring."
      }</p>`
    )
  );
  monitorGrid.appendChild(
    el(
      "article",
      "monitor-card",
      `<span class="label">Active leak pressure</span><strong>${findings.length}</strong><p>${
        findings.length
          ? "Current run has active leak detections. Review the action section for the next move."
          : "No active critical leak in the current run."
      }</p>`
    )
  );
  wrapper.appendChild(monitorGrid);

  if (analysis) {
    appendTopFindingCards(wrapper, findings);
  }

  const productPerformance = analysis?.features ? renderProductPerformance(analysis.features) : null;
  if (productPerformance) {
    wrapper.appendChild(productPerformance);
  }

  feed.appendChild(wrapper);
}

export function renderActionWorkspace(feed, { performance, analysis } = {}) {
  if (!feed) return;
  feed.innerHTML = "";

  const wrapper = workspaceSection(
    "Action center",
    "This is where leak detection becomes operating decisions. Pick the next move, log it, and watch impact over time."
  );

  const findings = Array.isArray(analysis && analysis.findings) ? analysis.findings : [];
  const feedback = performance && performance.action_feedback ? performance.action_feedback : null;

  if (findings.length) {
    const prioritized = [...findings].sort((left, right) => severityRank(right.severity) - severityRank(left.severity));
    const nextMoves = el("div", "action-list");
    prioritized.slice(0, 3).forEach((finding, index) => {
      nextMoves.appendChild(
        el(
          "article",
          "action-card",
          `
            <div class="action-card-head">
              <span class="action-priority">Priority ${index + 1}</span>
              <span class="severity">${finding.severity}</span>
            </div>
            <h3>${finding.title}</h3>
            <p class="action-change">${finding.what_changed || ""}</p>
            <p class="action-step"><strong>Do next:</strong> ${finding.what_to_do || "Assign an owner and act this week."}</p>
          `
        )
      );
    });
    wrapper.appendChild(nextMoves);
  } else {
    wrapper.appendChild(
      narrativeCard(
        "No urgent leak",
        "No active leak has crossed the current thresholds. Use this section to log actions and keep a clean operating record.",
        "good"
      )
    );
  }

  const feedbackPanel = el("section", "feedback-panel action-workspace-panel");
  feedbackPanel.appendChild(textEl("h3", "workspace-subheading", "Latest action feedback"));
  if (feedback) {
    feedbackPanel.appendChild(
      el(
        "p",
        "feedback-inline-meta",
        `<strong>Action:</strong> ${feedback.action_taken}<br><strong>Date:</strong> ${feedback.action_date}<br><strong>Reported:</strong> ${feedback.self_reported_outcome}<br><strong>Impact:</strong> <span class="impact-chip">${feedback.impact_label || "Pending"}</span>`
      )
    );
    if (feedback.impact_note) {
      feedbackPanel.appendChild(el("p", "sidebar-note", feedback.impact_note));
    }
  } else {
    feedbackPanel.appendChild(
      textEl("p", "sidebar-note", "No action feedback yet. Log the next action so the product can tie changes back to real decisions.")
    );
  }

  const form = el("form", "action-feedback-form workspace-action-form", actionFormMarkup("Save Action"));
  form.setAttribute("data-action-feedback-form", "true");
  feedbackPanel.appendChild(form);
  wrapper.appendChild(feedbackPanel);

  feed.appendChild(wrapper);
}

export function renderSidebarPerformance(container, payload, analysis = null, shopifyStatus = null) {
  if (!container) return;

  const summary = payload && payload.summary ? payload.summary : {};
  const points = Array.isArray(payload && payload.points) ? payload.points.length : 0;
  const findings = Array.isArray(analysis && analysis.findings) ? analysis.findings : [];

  container.innerHTML = "";
  const list = el("dl", "sidebar-kv-list");
  list.appendChild(el("div", "sidebar-kv-item", `<dt>Revenue</dt><dd>$${Number(summary.total_revenue || 0).toLocaleString()}</dd>`));
  list.appendChild(el("div", "sidebar-kv-item", `<dt>Repeat</dt><dd>${formatPct(summary.repeat_rate || 0)}</dd>`));
  list.appendChild(el("div", "sidebar-kv-item", `<dt>Refund</dt><dd>${formatPct(summary.refund_rate || 0)}</dd>`));
  list.appendChild(
    el(
      "div",
      "sidebar-kv-item",
      `<dt>WoW</dt><dd>${summary.week_over_week_revenue_change_pct === null || summary.week_over_week_revenue_change_pct === undefined
        ? "N/A"
        : `${Number(summary.week_over_week_revenue_change_pct).toFixed(2)}%`}</dd>`
    )
  );
  container.appendChild(list);
  container.appendChild(
    el(
      "p",
      "sidebar-note",
      `${points} run${points === 1 ? "" : "s"} in last ${payload && payload.window_days ? payload.window_days : 7} days. ${findings.length ? `${findings.length} active leak${findings.length === 1 ? "" : "s"} in current run.` : "No active leak in current run."}`
    )
  );
  container.appendChild(
    el(
      "p",
      "sidebar-note",
      shopifyStatus?.connected
        ? `Connected to ${shopifyStatus.shop_domain || "Shopify"}${shopifyStatus.last_synced_at ? ` • synced ${formatShortDate(shopifyStatus.last_synced_at)}` : ""}.`
        : "Shopify not connected yet."
    )
  );
}

export function renderSidebarActionFeedback(container, payload, analysis = null) {
  if (!container) return;
  container.innerHTML = "";
}

export function clearEmptyState(feed, empty) {
  if (empty && feed.contains(empty)) {
    feed.removeChild(empty);
  }
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
