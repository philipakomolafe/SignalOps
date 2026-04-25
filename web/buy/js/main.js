(function () {
  var TOKEN_STORAGE_KEY = "signalops_access_token";
  var RESUME_CHECKOUT_KEY = "signalops_resume_checkout";
  var params = new URLSearchParams(window.location.search);
  var plan = (params.get("plan") || "starter").trim().toLowerCase();
  var status = (params.get("status") || "").trim().toLowerCase();
  var returnPath = (params.get("return") || "").trim();
  var resume = (params.get("resume") || "").trim().toLowerCase();
  var shouldResumeCheckout = resume === "1" || resume === "true";
  var authToken = localStorage.getItem(TOKEN_STORAGE_KEY);
  var labelMap = {
    free: "Free",
    starter: "Starter ($29/mo)",
    pro: "Pro ($99/mo)",
  };
  var planFeaturesMap = {
    free: [
      "Single CSV analysis to test SignalOps quickly",
      "Core leak detection summary",
      "Runs history for your account",
      "Basic workspace access",
    ],
    starter: [
      "Unlimited CSV analyses",
      "Store, Runs, and Action workspaces",
      "Leak findings with operational diagnosis",
      "Weekly report email delivery",
      "Shopify integration setup",
      "Priority product updates",
    ],
    pro: [
      "Everything in Starter",
      "Shopify monitor-now automation",
      "Autonomous monitor endpoint for schedules",
      "Advanced monitoring + higher usage limits",
      "Team-ready operating workflow for retention/refund leaks",
      "Priority support and faster issue handling",
    ],
  };

  var planLabel = document.getElementById("planLabel");
  var planMeta = document.getElementById("planMeta");
  var statusText = document.getElementById("statusText");
  var checkoutBtn = document.getElementById("checkoutBtn");
  var accountBtn = document.getElementById("accountBtn");
  var activationBadge = document.getElementById("activationBadge");
  var offerPane = document.getElementById("offerPane");
  var offerLockText = document.getElementById("offerLockText");
  var paymentSummary = document.getElementById("paymentSummary");
  var summaryPlan = document.getElementById("summaryPlan");
  var summaryAmount = document.getElementById("summaryAmount");
  var summaryOptions = document.getElementById("summaryOptions");
  var summaryStatus = document.getElementById("summaryStatus");
  var planFeatureList = document.getElementById("planFeatureList");
  var canCheckout = false;
  var activationPollTimer = null;
  var flutterwaveScriptReady = false;

  function selectedPlanKey() {
    if (plan === "pro") {
      return "pro";
    }
    if (plan === "free") {
      return "free";
    }
    return "starter";
  }

  function renderPlanFeatures() {
    var key = selectedPlanKey();
    var features = planFeaturesMap[key] || planFeaturesMap.starter;
    var label = labelMap[key] || labelMap.starter;

    function listMarkup(items) {
      return items.map(function (item) {
        return "<li>" + item + "</li>";
      }).join("");
    }

    if (planFeatureList) {
      planFeatureList.innerHTML = listMarkup(features);
    }
    if (summaryPlan) {
      summaryPlan.textContent = label;
    }
  }

  function setOfferPaneReady(ready, lockMessage) {
    if (!offerPane) {
      return;
    }
    offerPane.classList.toggle("is-locked", !ready);
    offerPane.classList.toggle("is-ready", !!ready);
    if (offerLockText) {
      offerLockText.textContent = lockMessage || "";
    }
    if (paymentSummary) {
      paymentSummary.hidden = !ready;
    }
  }

  function setPaymentSummary(payload) {
    if (!payload) return;
    if (summaryAmount) {
      var amountText = "$" + Number(payload.amount || 0).toLocaleString() + " / month";
      summaryAmount.textContent = amountText;
    }
    if (summaryOptions) {
      summaryOptions.textContent = "Card, bank transfer, USSD";
    }
    if (summaryStatus) {
      summaryStatus.textContent = "Flutterwave ready";
    }
  }

  function waitForFlutterwaveReady() {
    var checks = 0;
    var maxChecks = 25;
    var timer = window.setInterval(function () {
      checks += 1;
      if (typeof window.FlutterwaveCheckout === "function") {
        flutterwaveScriptReady = true;
        window.clearInterval(timer);
        setOfferPaneReady(true, "");
        return;
      }
      if (checks >= maxChecks) {
        window.clearInterval(timer);
        flutterwaveScriptReady = false;
        setOfferPaneReady(false, "Payment engine unavailable. Refresh and try again.");
      }
    }, 180);

    if (typeof window.FlutterwaveCheckout === "function") {
      flutterwaveScriptReady = true;
      window.clearInterval(timer);
      setOfferPaneReady(true, "");
    }
  }

  function setCheckoutState(enabled, text) {
    if (!checkoutBtn) {
      return;
    }
    checkoutBtn.textContent = text || "Continue to checkout";
    canCheckout = !!enabled;
    if (enabled) {
      checkoutBtn.style.pointerEvents = "auto";
      checkoutBtn.style.opacity = "1";
      checkoutBtn.setAttribute("aria-disabled", "false");
      checkoutBtn.disabled = false;
    } else {
      checkoutBtn.style.pointerEvents = "none";
      checkoutBtn.style.opacity = "0.5";
      checkoutBtn.setAttribute("aria-disabled", "true");
      checkoutBtn.disabled = true;
    }
  }

  function setStatus(message) {
    if (statusText) {
      statusText.textContent = message;
    }
  }

  function setActivationBadge(state, message) {
    if (!activationBadge) {
      return;
    }
    activationBadge.classList.remove("is-hidden", "is-pending", "is-success", "is-error");
    if (state === "hidden") {
      activationBadge.classList.add("is-hidden");
      activationBadge.textContent = "";
      return;
    }

    if (state === "pending") {
      activationBadge.classList.add("is-pending");
    } else if (state === "success") {
      activationBadge.classList.add("is-success");
    } else {
      activationBadge.classList.add("is-error");
    }
    activationBadge.textContent = message;
  }

  function isPlanActivatedForSelection(selectedPlan, currentPlan) {
    var safeSelected = (selectedPlan || "").toLowerCase();
    var safeCurrent = (currentPlan || "").toLowerCase();
    if (safeSelected === "starter") {
      return safeCurrent === "starter" || safeCurrent === "pro" || safeCurrent === "admin";
    }
    if (safeSelected === "pro") {
      return safeCurrent === "pro" || safeCurrent === "admin";
    }
    return false;
  }

  function stopActivationPolling() {
    if (activationPollTimer) {
      window.clearInterval(activationPollTimer);
      activationPollTimer = null;
    }
  }

  function startActivationPolling() {
    if (!authToken || (plan !== "starter" && plan !== "pro")) {
      return;
    }

    stopActivationPolling();
    setActivationBadge("pending", "Activation check in progress...");

    var attempts = 0;
    var maxAttempts = 24;

    function checkPlanActivation() {
      attempts += 1;
      fetch("/api/v1/account/plan", {
        method: "GET",
        headers: {
          Authorization: "Bearer " + authToken,
        },
      })
        .then(function (response) {
          if (response.status === 401) {
            localStorage.removeItem(TOKEN_STORAGE_KEY);
            throw new Error("Authentication required");
          }
          if (!response.ok) {
            throw new Error("Plan check failed (" + response.status + ")");
          }
          return response.json();
        })
        .then(function (payload) {
          var currentPlan = payload && payload.plan_code ? String(payload.plan_code) : "free";
          if (isPlanActivatedForSelection(plan, currentPlan)) {
            stopActivationPolling();
            setActivationBadge("success", "Subscription activated. Your account is ready.");
            setStatus("Payment verified and subscription activated.");
            if (accountBtn) {
              accountBtn.href = "/dashboard/";
            }
            window.setTimeout(function () {
              window.location.href = dashboardReturnUrl("activated");
            }, 900);
            return;
          }

          if (attempts >= maxAttempts) {
            stopActivationPolling();
            setActivationBadge(
              "error",
              "Activation is still pending. Refresh in a moment or contact support if this persists."
            );
          }
        })
        .catch(function (error) {
          stopActivationPolling();
          if (String(error && error.message).toLowerCase().indexOf("authentication") >= 0) {
            setActivationBadge("error", "Session expired. Log in again to confirm activation.");
            return;
          }
          setActivationBadge("error", "Could not confirm activation right now.");
        });
    }

    checkPlanActivation();
    activationPollTimer = window.setInterval(function () {
      if (attempts >= maxAttempts) {
        stopActivationPolling();
        return;
      }
      checkPlanActivation();
    }, 5000);
  }

  function loginUrlForCurrentPlan() {
    var nextPath = "/buy/?plan=" + encodeURIComponent(plan) + "&resume=1";
    if (returnPath) {
      nextPath += "&return=" + encodeURIComponent(returnPath);
    }
    return "/login/?next=" + encodeURIComponent(nextPath);
  }

  function dashboardReturnUrl(state) {
    var safePath = returnPath;
    if (!safePath || safePath.charAt(0) !== "/" || safePath.slice(0, 2) === "//") {
      safePath = "/dashboard/";
    }

    var joiner = safePath.indexOf("?") >= 0 ? "&" : "?";
    if (safePath.indexOf("billing=") >= 0) {
      return safePath;
    }
    return safePath + joiner + "billing=" + encodeURIComponent(state || "activated");
  }

  function initializeCheckout() {
    if (plan === "free") {
      window.location.href = "/login/#register";
      return;
    }

    if (!authToken) {
      setStatus("Login is required before payment checkout.");
      try {
        sessionStorage.setItem(
          RESUME_CHECKOUT_KEY,
          JSON.stringify({
            plan: plan,
            returnPath: returnPath || "",
            createdAt: Date.now(),
          })
        );
      } catch (_error) {
        // Ignore storage failures and continue redirect flow.
      }
      window.location.href = loginUrlForCurrentPlan();
      return;
    }

    setCheckoutState(false, "Preparing secure checkout...");
    setStatus("Initializing secure payment session...");
    if (summaryStatus) {
      summaryStatus.textContent = "Initializing";
    }

    fetch("/api/v1/payments/flutterwave/initialize", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + authToken,
      },
      body: JSON.stringify({ plan: plan }),
    })
      .then(function (response) {
        if (response.status === 401) {
          localStorage.removeItem(TOKEN_STORAGE_KEY);
          throw new Error("Authentication required");
        }
        if (!response.ok) {
          throw new Error("Checkout initialization failed (" + response.status + ")");
        }
        return response.json();
      })
      .then(function (payload) {
        if (typeof window.FlutterwaveCheckout !== "function") {
          throw new Error("Flutterwave checkout script is unavailable");
        }
        flutterwaveScriptReady = true;
        setOfferPaneReady(true, "");
        setPaymentSummary(payload);

        setCheckoutState(true, "Continue to secure checkout");
        window.FlutterwaveCheckout({
          public_key: payload.public_key,
          tx_ref: payload.tx_ref,
          amount: payload.amount,
          currency: payload.currency,
          payment_options: "card,banktransfer,ussd",
          payment_plan: payload.payment_plan,
          customer: {
            email: payload.customer_email,
            name: payload.customer_name,
          },
          customizations: {
            title: payload.customization_title || "SignalOps Subscription",
            description: payload.customization_description || "SignalOps plan checkout",
          },
          callback: function () {
            var nextUrl = "/buy/?plan=" + encodeURIComponent(plan) + "&status=success";
            if (returnPath) {
              nextUrl += "&return=" + encodeURIComponent(returnPath);
            }
            window.location.href = nextUrl;
          },
          onclose: function () {
            if (summaryStatus) {
              summaryStatus.textContent = "Closed";
            }
            setStatus("Checkout closed. You can try again anytime.");
          },
        });
      })
      .catch(function (error) {
        setCheckoutState(true, "Continue to secure checkout");
        if (summaryStatus) {
          summaryStatus.textContent = "Unavailable";
        }
        if (String(error && error.message).toLowerCase().indexOf("authentication") >= 0) {
          setStatus("Your session expired. Please log in again.");
          window.location.href = loginUrlForCurrentPlan();
          return;
        }
        setStatus("Could not initialize checkout. Please try again.");
      });
  }

  if (planLabel) {
    planLabel.textContent = "Selected plan: " + (labelMap[plan] || "Starter ($29/mo)");
  }
  if (planMeta) {
    planMeta.textContent = "Plan key: " + (labelMap[plan] ? plan : "starter");
  }
  if (summaryAmount) {
    summaryAmount.textContent = plan === "pro" ? "$99 / month" : plan === "free" ? "$0 / month" : "$29 / month";
  }
  if (summaryStatus) {
    summaryStatus.textContent = "Waiting for Flutterwave";
  }
  renderPlanFeatures();
  setOfferPaneReady(false, "Waiting for secure payment engine...");
  waitForFlutterwaveReady();

  if (status === "success") {
    setStatus("Payment submitted. We are verifying your transaction now.");
    setActivationBadge("pending", "Waiting for secure webhook verification...");
    startActivationPolling();
  } else {
    setActivationBadge("hidden", "");
  }
  if (status === "cancelled") {
    setStatus("Checkout cancelled. You can try again anytime.");
  }

  setCheckoutState(false, "Preparing checkout...");

  if (checkoutBtn) {
    checkoutBtn.addEventListener("click", function () {
      if (!canCheckout) {
        return;
      }
      initializeCheckout();
    });
  }

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

      if (plan === "free") {
        setCheckoutState(true, "Continue with free plan");
        setOfferPaneReady(true, "");
        if (summaryStatus) {
          summaryStatus.textContent = "No payment required";
        }
        if (accountBtn) {
          accountBtn.href = "/login/#register";
        }
      } else {
        setCheckoutState(enabled, enabled ? "Continue to secure checkout" : "Checkout unavailable");
        if (!flutterwaveScriptReady && enabled) {
          setOfferPaneReady(false, "Waiting for secure payment engine...");
        }
        if (accountBtn) {
          accountBtn.href = authToken ? "/dashboard/" : loginUrlForCurrentPlan();
        }

        if (enabled && authToken && shouldResumeCheckout && !status) {
          try {
            sessionStorage.removeItem(RESUME_CHECKOUT_KEY);
          } catch (_error) {
            // Non-blocking cleanup.
          }
          initializeCheckout();
          return;
        }
      }

      if (!status) {
        setStatus(message);
      }
    })
    .catch(function () {
      setCheckoutState(false, "Checkout unavailable");
      setStatus("Could not load checkout details. Please try again.");
    });
})();
