(function () {
  var TOKEN_STORAGE_KEY = "signalops_access_token";
  var API_BASE = (window.SIGNALOPS_API_BASE || window.location.origin || "").replace(/\/$/, "");
  var ENDPOINT = API_BASE + "/api/v1/admin/founder-metrics";

  var statusEl = document.getElementById("status");
  var refreshBtn = document.getElementById("refreshBtn");

  function setText(id, value) {
    var node = document.getElementById(id);
    if (!node) return;
    node.textContent = value;
  }

  function setStatus(message, isError) {
    if (!statusEl) return;
    statusEl.textContent = message;
    statusEl.classList.toggle("error", !!isError);
  }

  function fmtMoney(amount) {
    return "$" + Number(amount || 0).toLocaleString(undefined, { maximumFractionDigits: 2 });
  }

  function fmtPct(value) {
    if (value === null || value === undefined) return "N/A";
    return Number(value).toFixed(2) + "%";
  }

  function renderTrend(rows) {
    var list = document.getElementById("turnaroundTrend");
    if (!list) return;
    list.innerHTML = "";

    if (!Array.isArray(rows) || rows.length === 0) {
      var empty = document.createElement("li");
      empty.textContent = "No turnaround trend data yet. Run more analyses to populate this.";
      list.appendChild(empty);
      return;
    }

    rows.forEach(function (row) {
      var li = document.createElement("li");
      li.textContent = row.day + ": " + Number(row.avg_duration_ms || 0).toFixed(0) + " ms";
      list.appendChild(li);
    });
  }

  function renderPlans(rows) {
    var list = document.getElementById("plansList");
    if (!list) return;
    list.innerHTML = "";

    if (!Array.isArray(rows) || rows.length === 0) {
      var empty = document.createElement("li");
      empty.textContent = "No active subscriptions yet.";
      list.appendChild(empty);
      return;
    }

    rows.forEach(function (row) {
      var li = document.createElement("li");
      li.textContent = String(row.plan_code || "unknown") + ": " + Number(row.total || 0);
      list.appendChild(li);
    });
  }

  function requireAuthToken() {
    var token = localStorage.getItem(TOKEN_STORAGE_KEY);
    if (!token) {
      window.location.replace("/login/");
      return null;
    }
    return token;
  }

  function render(payload) {
    var product = payload.product_impact || {};
    var usage = payload.usage_velocity || {};
    var monitoring = payload.monitoring_reliability || {};
    var commercial = payload.commercial_traction || {};

    setText("totalRevenue", fmtMoney(product.total_revenue_analyzed));
    setText("repeatRate", fmtPct(product.repeat_rate));
    setText("refundRate", fmtPct(product.refund_rate));
    setText("wowRevenue", fmtPct(product.week_over_week_revenue_change_pct));

    var meta = [];
    if (product.based_on_run_id) {
      meta.push("Based on run #" + product.based_on_run_id);
    }
    if (product.based_on_created_at) {
      meta.push("at " + product.based_on_created_at);
    }
    setText("productMeta", meta.join(" "));

    setText("analyses7d", String(usage.analyses_run_7d || 0));
    setText("activeUsers7d", String(usage.active_users_7d || 0));
    renderTrend(usage.csv_to_insight_turnaround_trend || []);

    setText("monitorRuns7d", String(monitoring.monitor_runs_7d || 0));
    setText("successRate", fmtPct(monitoring.success_rate_pct));
    setText("errorCount7d", String(monitoring.error_count_7d || 0));
    setText("topErrorCategory", monitoring.top_error_category || "N/A");

    setText("signups7d", String(commercial.new_signups_7d || 0));
    setText("paymentEvents7d", String(commercial.payment_success_events_7d || 0));
    renderPlans(commercial.active_subscriptions_by_plan || []);

    setStatus(
      "Metrics refreshed. Window: " + String(payload.window_days || 7) + " days. Generated at " + (payload.generated_at || "N/A"),
      false
    );
  }

  function loadMetrics() {
    var token = requireAuthToken();
    if (!token) return;

    setStatus("Loading metrics...", false);
    fetch(ENDPOINT, {
      headers: {
        Authorization: "Bearer " + token,
      },
    })
      .then(function (response) {
        if (response.status === 401) {
          localStorage.removeItem(TOKEN_STORAGE_KEY);
          window.location.replace("/login/");
          throw new Error("Unauthorized");
        }
        if (response.status === 403) {
          throw new Error("Access denied. This page is admin-only.");
        }
        if (response.status === 503) {
          throw new Error("Admin access not configured yet. Set ADMIN_EMAILS in backend env.");
        }
        if (!response.ok) {
          throw new Error("Failed to load admin metrics.");
        }
        return response.json();
      })
      .then(render)
      .catch(function (error) {
        setStatus(error.message || "Failed to load metrics.", true);
      });
  }

  if (refreshBtn) {
    refreshBtn.addEventListener("click", loadMetrics);
  }

  loadMetrics();
})();
