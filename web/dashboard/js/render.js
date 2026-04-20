function el(tag, className, html) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (html !== undefined) node.innerHTML = html;
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

export function renderPerformanceDefault(feed, payload) {
  const summary = payload && payload.summary ? payload.summary : {};
  const wrapper = el("article", "feed-message system");
  wrapper.appendChild(el("h3", "", "7-Day Store Performance"));
  wrapper.appendChild(
    el(
      "p",
      "",
      "This is your rolling business view. Use Recent Analyses in the sidebar to open individual run snapshots."
    )
  );

  const metricsGrid = el("div", "metrics-grid");
  metricsGrid.appendChild(metric("Total Revenue", formatCurrency(summary.total_revenue || 0)));
  metricsGrid.appendChild(metric("Orders", Number(summary.order_count || 0).toLocaleString()));
  metricsGrid.appendChild(metric("Customers", Number(summary.customer_count || 0).toLocaleString()));
  metricsGrid.appendChild(metric("Revenue/User", formatCurrency(summary.revenue_per_user || 0)));
  metricsGrid.appendChild(metric("Purchase Frequency", Number(summary.purchase_frequency || 0).toFixed(2)));
  metricsGrid.appendChild(
    metric(
      "WoW Revenue",
      summary.week_over_week_revenue_change_pct === null || summary.week_over_week_revenue_change_pct === undefined
        ? "N/A"
        : formatPct(summary.week_over_week_revenue_change_pct)
    )
  );
  wrapper.appendChild(metricsGrid);

  const points = Array.isArray(payload && payload.points) ? payload.points.length : 0;
  wrapper.appendChild(
    el(
      "p",
      "",
      `Combined from ${points} runs over ${payload && payload.window_days ? payload.window_days : 7} days.`
    )
  );

  const feedback = payload && payload.action_feedback ? payload.action_feedback : null;
  const feedbackState = feedback?.impact_label || (feedback ? "Pending" : "Not started");
  const feedbackDisclosure = disclosure("Action feedback", `Status: ${feedbackState}`);
  const feedbackBox = el("section", "feedback-panel");
  if (feedback) {
    const impactLabel = feedback.impact_label || "Pending";
    feedbackBox.appendChild(
      el(
        "p",
        "feedback-inline-meta",
        `<strong>Latest action:</strong> ${feedback.action_taken}<br><strong>Date:</strong> ${feedback.action_date}<br><strong>Reported:</strong> ${feedback.self_reported_outcome}<br><strong>Impact:</strong> <span class="impact-chip">${impactLabel}</span>`
      )
    );
    if (feedback.impact_note) {
      feedbackBox.appendChild(el("p", "", feedback.impact_note));
    }
  } else {
    feedbackBox.appendChild(el("p", "", "No action feedback yet. Add one to track before/after impact."));
  }
  feedbackDisclosure.appendChild(feedbackBox);
  wrapper.appendChild(feedbackDisclosure);
  feedbackBox.appendChild(
    el(
      "form",
      "",
      `
        <label class="label" for="action-taken-input">What action did you take?</label>
        <input id="action-taken-input" name="action_taken" type="text" maxlength="500" required />
        <label class="label" for="action-date-input">When?</label>
        <input id="action-date-input" name="action_date" type="date" required />
        <label class="label" for="action-outcome-input">Did it help?</label>
        <select id="action-outcome-input" name="self_reported_outcome" required>
          <option value="yes">yes</option>
          <option value="no">no</option>
          <option value="unsure" selected>unsure</option>
        </select>
        <button id="action-feedback-submit" type="submit">Save Feedback</button>
      `
    )
  );
  feedbackBox.querySelector("form")?.setAttribute("id", "action-feedback-form");

  feed.appendChild(wrapper);
}

export function renderSidebarPerformance(container, payload) {
  if (!container) return;

  const summary = payload && payload.summary ? payload.summary : {};
  const points = Array.isArray(payload && payload.points) ? payload.points.length : 0;

  container.innerHTML = "";
  const list = el("dl", "sidebar-kv-list");
  list.appendChild(el("div", "sidebar-kv-item", `<dt>Revenue</dt><dd>$${Number(summary.total_revenue || 0).toLocaleString()}</dd>`));
  list.appendChild(el("div", "sidebar-kv-item", `<dt>Orders</dt><dd>${Number(summary.order_count || 0).toLocaleString()}</dd>`));
  list.appendChild(el("div", "sidebar-kv-item", `<dt>Customers</dt><dd>${Number(summary.customer_count || 0).toLocaleString()}</dd>`));
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
  container.appendChild(el("p", "sidebar-note", `${points} run${points === 1 ? "" : "s"} in last ${payload && payload.window_days ? payload.window_days : 7} days.`));
}

export function renderSidebarActionFeedback(container, payload) {
  if (!container) return;

  const feedback = payload && payload.action_feedback ? payload.action_feedback : null;
  const status = feedback?.impact_label || (feedback ? "Pending" : "Not started");

  container.innerHTML = "";
  container.appendChild(el("p", "sidebar-note", `Status: ${status}`));

  if (feedback) {
    const impactLabel = feedback.impact_label || "Pending";
    container.appendChild(
      el(
        "p",
        "feedback-inline-meta",
        `<strong>Latest:</strong> ${feedback.action_taken}<br><strong>Date:</strong> ${feedback.action_date}<br><strong>Reported:</strong> ${feedback.self_reported_outcome}<br><strong>Impact:</strong> <span class="impact-chip">${impactLabel}</span>`
      )
    );
    if (feedback.impact_note) {
      container.appendChild(el("p", "sidebar-note", feedback.impact_note));
    }
  } else {
    container.appendChild(el("p", "sidebar-note", "No action feedback yet."));
  }

  container.appendChild(
    el(
      "form",
      "sidebar-feedback-form",
      `
        <label class="label" for="action-taken-input">What action?</label>
        <input id="action-taken-input" name="action_taken" type="text" maxlength="500" required />
        <label class="label" for="action-date-input">When?</label>
        <input id="action-date-input" name="action_date" type="date" required />
        <label class="label" for="action-outcome-input">Did it help?</label>
        <select id="action-outcome-input" name="self_reported_outcome" required>
          <option value="yes">yes</option>
          <option value="no">no</option>
          <option value="unsure" selected>unsure</option>
        </select>
        <button id="action-feedback-submit" type="submit">Save</button>
      `
    )
  );
  container.querySelector("form")?.setAttribute("id", "action-feedback-form");
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

export function renderHistoryList(historyListEl, rows, onClick) {
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
    button.className = "history-item";
    button.innerHTML = `<strong>#${row.run_id} ${row.source_file}</strong><span>${row.created_at}</span>`;
    button.addEventListener("click", () => onClick(row.run_id));
    item.appendChild(button);
    historyListEl.appendChild(item);
  });
}
