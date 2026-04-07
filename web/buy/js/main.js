(function () {
  var params = new URLSearchParams(window.location.search);
  var plan = (params.get("plan") || "starter").trim().toLowerCase();
  var status = (params.get("status") || "").trim().toLowerCase();
  var shouldAutoRedirect = !status;
  var labelMap = {
    free: "Free",
    starter: "Starter ($29/mo)",
    pro: "Pro ($99/mo)",
  };

  var planLabel = document.getElementById("planLabel");
  var planMeta = document.getElementById("planMeta");
  var statusText = document.getElementById("statusText");
  var checkoutBtn = document.getElementById("checkoutBtn");
  var accountBtn = document.getElementById("accountBtn");

  function setCheckoutState(enabled, url, text) {
    if (!checkoutBtn) {
      return;
    }
    checkoutBtn.textContent = text || "Continue to checkout";
    if (enabled && url) {
      checkoutBtn.href = url;
      checkoutBtn.style.pointerEvents = "auto";
      checkoutBtn.style.opacity = "1";
      checkoutBtn.setAttribute("aria-disabled", "false");
    } else {
      checkoutBtn.href = "#";
      checkoutBtn.style.pointerEvents = "none";
      checkoutBtn.style.opacity = "0.5";
      checkoutBtn.setAttribute("aria-disabled", "true");
    }
  }

  if (planLabel) {
    planLabel.textContent = "Selected plan: " + (labelMap[plan] || "Starter ($29/mo)");
  }
  if (planMeta) {
    planMeta.textContent = "Plan key: " + (labelMap[plan] ? plan : "starter");
  }

  if (statusText && status === "success") {
    statusText.textContent = "Payment submitted. We are verifying your transaction now.";
  }
  if (statusText && status === "cancelled") {
    statusText.textContent = "Checkout cancelled. You can try again anytime.";
  }

  setCheckoutState(false, "", "Preparing checkout...");

  fetch("/api/v1/buy?plan=" + encodeURIComponent(plan), { method: "GET" })
    .then(function (response) {
      if (!response.ok) {
        throw new Error("Buy API returned " + response.status);
      }
      return response.json();
    })
    .then(function (payload) {
      var message = payload && payload.message ? payload.message : "Buy API is ready.";
      var enabled = !!(payload && payload.checkout_enabled);
      var checkoutUrl = payload && payload.checkout_url ? payload.checkout_url : "";

      if (plan === "free") {
        setCheckoutState(true, "/login/#register", "Continue with free plan");
        if (accountBtn) {
          accountBtn.href = "/login/#register";
        }
      } else {
        setCheckoutState(enabled, checkoutUrl, enabled ? "Continue to secure checkout" : "Checkout unavailable");
        if (accountBtn) {
          accountBtn.href = "/login/";
        }

        if (enabled && checkoutUrl && shouldAutoRedirect) {
          window.location.href = checkoutUrl;
          return;
        }
      }

      if (statusText) {
        statusText.textContent = message;
      }
    })
    .catch(function () {
      setCheckoutState(false, "", "Checkout unavailable");
      if (statusText) {
        statusText.textContent = "Could not load checkout details. Please try again.";
      }
    });
})();
