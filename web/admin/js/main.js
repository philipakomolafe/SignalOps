(function () {
  var TOKEN_STORAGE_KEY = "signalops_access_token";
  var API_BASE = (window.SIGNALOPS_API_BASE || window.location.origin || "").replace(/\/$/, "");
  var ENDPOINT = API_BASE + "/api/v1/admin/feature-timeseries";
  var activeDays = 30;

  var statusEl = document.getElementById("status");
  var refreshBtn = document.getElementById("refreshBtn");
  var rangeActions = document.getElementById("rangeActions");
  var windowMeta = document.getElementById("windowMeta");

  var METRICS = [
    { key: "total_revenue", format: formatMoney },
    { key: "order_count", format: formatNumber },
    { key: "customer_count", format: formatNumber },
    { key: "revenue_per_user", format: formatMoney },
    { key: "purchase_frequency", format: formatNumber },
    { key: "repeat_rate", format: formatPercent },
    { key: "refund_rate", format: formatPercent },
    { key: "week_over_week_revenue_change_pct", format: formatPercent },
  ];

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

  function formatMoney(amount) {
    return "$" + Number(amount || 0).toLocaleString(undefined, { maximumFractionDigits: 2 });
  }

  function formatPercent(value) {
    if (value === null || value === undefined) return "N/A";
    return Number(value).toFixed(2) + "%";
  }

  function formatNumber(value) {
    return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 });
  }

  function setValue(metricKey, valueText) {
    var node = document.getElementById("value-" + metricKey);
    if (node) {
      node.textContent = valueText;
    }
  }

  function getSeries(points, metricKey) {
    return points
      .map(function (point) {
        var raw = point[metricKey];
        if (raw === null || raw === undefined) {
          return null;
        }
        var value = Number(raw);
        return Number.isFinite(value) ? value : null;
      })
      .filter(function (value) {
        return value !== null;
      });
  }

  function drawSparkline(metricKey, values) {
    var canvas = document.getElementById("chart-" + metricKey);
    if (!canvas) {
      return;
    }
    var ctx = canvas.getContext("2d");
    if (!ctx) {
      return;
    }

    var width = canvas.width;
    var height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    ctx.strokeStyle = "#d8d8d8";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, height - 24);
    ctx.lineTo(width, height - 24);
    ctx.stroke();

    if (!values || values.length === 0) {
      return;
    }

    var min = Math.min.apply(null, values);
    var max = Math.max.apply(null, values);
    var spread = max - min || 1;
    var xStep = values.length > 1 ? (width - 12) / (values.length - 1) : 0;

    ctx.strokeStyle = "#111111";
    ctx.lineWidth = 2;
    ctx.beginPath();

    for (var i = 0; i < values.length; i += 1) {
      var x = 6 + xStep * i;
      var y = height - 28 - ((values[i] - min) / spread) * (height - 48);
      if (i === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    }
    ctx.stroke();
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
    var points = Array.isArray(payload.points) ? payload.points : [];
    METRICS.forEach(function (metric) {
      var values = getSeries(points, metric.key);
      var latest = values.length ? values[values.length - 1] : null;
      setValue(metric.key, latest === null ? "N/A" : metric.format(latest));
      drawSparkline(metric.key, values);
    });

    if (windowMeta) {
      windowMeta.textContent =
        "Showing " + String(points.length) + " points over " + String(payload.window_days || activeDays) + " days.";
    }

    setStatus("Metrics refreshed at " + (payload.generated_at || "N/A"), false);
  }

  function loadMetrics() {
    var token = requireAuthToken();
    if (!token) return;

    setStatus("Loading metrics...", false);
    fetch(ENDPOINT + "?days=" + encodeURIComponent(String(activeDays)), {
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

  function wireRangeButtons() {
    if (!rangeActions) {
      return;
    }
    rangeActions.addEventListener("click", function (event) {
      var target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      var daysAttr = target.getAttribute("data-days");
      if (!daysAttr) {
        return;
      }
      var parsed = Number(daysAttr);
      if (!Number.isFinite(parsed) || parsed <= 0) {
        return;
      }
      activeDays = parsed;

      var buttons = rangeActions.querySelectorAll(".range-btn");
      buttons.forEach(function (btn) {
        btn.classList.remove("active");
      });
      target.classList.add("active");
      loadMetrics();
    });
  }

  if (refreshBtn) {
    refreshBtn.addEventListener("click", loadMetrics);
  }
  wireRangeButtons();

  loadMetrics();
})();
