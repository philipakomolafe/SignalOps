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
  wrapper.appendChild(diagnosisGrid);

  const features = payload.features || {};
  const metricsGrid = el("div", "metrics-grid");
  metricsGrid.appendChild(metric("Total Revenue", `$${Number(features.total_revenue || 0).toLocaleString()}`));
  metricsGrid.appendChild(metric("Revenue/User", `$${Number(features.revenue_per_user || 0).toLocaleString()}`));
  metricsGrid.appendChild(metric("Purchase Frequency", Number(features.purchase_frequency || 0).toFixed(2)));
  metricsGrid.appendChild(metric("Repeat Rate", `${Number(features.repeat_rate || 0).toFixed(2)}%`));
  metricsGrid.appendChild(metric("Refund Rate", `${Number(features.refund_rate || 0).toFixed(2)}%`));
  metricsGrid.appendChild(metric(
    "WoW Revenue",
    features.week_over_week_revenue_change_pct === null || features.week_over_week_revenue_change_pct === undefined
      ? "N/A"
      : `${Number(features.week_over_week_revenue_change_pct).toFixed(2)}%`
  ));
  wrapper.appendChild(metricsGrid);

  const findingsTitle = el("h3", "", "Leak Findings");
  findingsTitle.style.marginTop = "0.75rem";
  wrapper.appendChild(findingsTitle);

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
  wrapper.appendChild(findingsGrid);

  feed.appendChild(wrapper);
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
