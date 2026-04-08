# Standard library imports for hashing, logging, timing, tokens, and filesystem paths.
import hashlib
import json
import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# FastAPI primitives for app, request handling, dependency injection, and file uploads.
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
# CORS middleware allows browser clients from configured origins to call the API.
from fastapi.middleware.cors import CORSMiddleware
# RedirectResponse is used for canonical URL redirects and root redirects.
from fastapi.responses import RedirectResponse
# StaticFiles serves frontend assets (dashboard, login, landing pages).
from fastapi.staticfiles import StaticFiles

# App-level runtime settings (app name/version/cors config).
from app.configs.settings import settings
# Typed request/response models used by auth and analysis endpoints.
from app.models.schemas import (
    AccountPlanResponse,
    AdminFeatureTimeSeriesResponse,
    AuthUser,
    AnalysisHistoryItem,
    AnalysisResponse,
    DataRetentionRunResponse,
    FounderPostPackMetricsResponse,
    LoginRequest,
    LoginResponse,
    MonitorRunResponse,
    ShopifyConnectionStatusResponse,
    ShopifyConnectStartRequest,
    ShopifyConnectStartResponse,
    SignupRequest,
    SignupResponse,
)
# Feature engineering helpers for analytics calculations.
from app.services.features import compute_comparison_windows, generate_feature_snapshot
# CSV normalization helper and explicit normalization error type.
from app.services.ingestion import CSVNormalizationError, normalize_orders_csv, normalize_shopify_orders
# Leak rule engine that generates findings from computed features.
from app.services.leak_engine import detect_leaks
# Auth utility helpers to keep this module focused on API orchestration.
from app.services.auth_utils import (
    extract_bearer_token,
    hash_password,
    hash_token,
    mask_email,
    verify_password,
)
# Persistence layer for users, sessions, analysis history, and caching.
from app.services.persistence import (
    DuplicateEmailError,
    create_signup,
    create_session,
    deactivate_shopify_connection,
    find_analysis_by_hash,
    get_analysis,
    get_active_billing_subscription_by_user,
    get_admin_feature_timeseries,
    get_shopify_connection_by_user,
    get_user_by_email,
    get_user_by_session_hash,
    init_storage,
    list_analyses,
    list_active_shopify_connections,
    mark_shopify_connection_synced,
    revoke_session,
    run_data_retention,
    save_analysis_timing,
    save_payment_event,
    save_monitor_run,
    save_analysis,
    get_founder_post_pack_metrics,
    upsert_billing_subscription,
    update_shopify_connection_tokens,
    upsert_shopify_connection,
)
# Report builder that converts findings into summary + diagnosis text.
from app.services.report_generator import build_report
from app.services.flutterwave import (
    checkout_link_for_plan,
    is_valid_webhook_signature,
    verify_transaction,
)
from app.services.shopify import (
    build_install_url,
    build_oauth_state,
    exchange_code_for_token,
    fetch_orders,
    migrate_legacy_offline_access_token,
    normalize_shop_domain,
    parse_oauth_state,
    refresh_offline_access_token,
    verify_callback_hmac,
    verify_webhook_hmac,
)


logger = logging.getLogger(__name__)


if not logging.getLogger().handlers:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


# FastAPI application object with metadata used by docs/clients.
app = FastAPI(title=settings.app_name, version=settings.app_version)

# Absolute path to the frontend web folder (sibling of app folder).
WEB_ROOT = Path(__file__).resolve().parent.parent / "web"

# Build allowed CORS origins list from comma-separated config.
origins = [origin.strip() for origin in settings.cors_allow_origins.split(",") if origin.strip()]
# Register CORS middleware so frontend browser apps can call this backend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log request/response lifecycle for observability."""
    started_at = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Unhandled error during %s %s", request.method, request.url.path)
        raise

    elapsed = time.perf_counter() - started_at
    logger.info("%s %s -> %s in %.3fs", request.method, request.url.path, response.status_code, elapsed)
    return response


@app.middleware("http")
async def canonicalize_index_html(request: Request, call_next):
    """Redirect long file-style URLs to canonical clean routes.

    Examples:
    - /dashboard/index.html -> /dashboard/
    - /index.html -> /
    """
    # Current request path (without query string).
    path = request.url.path
    # Root index page should always become the root path.
    if path == "/index.html":
        destination = "/"
        # Preserve any query parameters while redirecting.
        if request.url.query:
            destination = f"{destination}?{request.url.query}"
        # 308 keeps method/body semantics intact on redirect.
        return RedirectResponse(url=destination, status_code=308)

    # Any nested index.html path should become its clean directory route.
    if path.endswith("/index.html"):
        # Remove only the trailing "index.html" segment.
        destination = path[: -len("index.html")]
        # Preserve query string if provided.
        if request.url.query:
            destination = f"{destination}?{request.url.query}"
        # 308 avoids accidental method changes in non-GET scenarios.
        return RedirectResponse(url=destination, status_code=308)

    # Non-index routes continue through the normal request pipeline.
    return await call_next(request)


# Mount frontend folders only when they exist on disk.
if WEB_ROOT.exists():
    # Shared assets from web root (e.g., logo file).
    app.mount("/assets", StaticFiles(directory=WEB_ROOT / "assets", html=False), name="assets")
    # Dashboard app (protected in frontend by auth token checks).
    app.mount("/dashboard", StaticFiles(directory=WEB_ROOT / "dashboard", html=True), name="dashboard")
    # Combined login/register auth page.
    app.mount("/login", StaticFiles(directory=WEB_ROOT / "login", html=True), name="login")
    # Legacy signup URL retained as redirect page.
    app.mount("/signup", StaticFiles(directory=WEB_ROOT / "signup", html=True), name="signup")
    # Landing page variant 1.
    app.mount("/v1", StaticFiles(directory=WEB_ROOT / "v1", html=True), name="v1")
    # Placeholder buy page for checkout flow.
    app.mount("/buy", StaticFiles(directory=WEB_ROOT / "buy", html=True), name="buy")
    # Admin metrics page.
    app.mount("/admin", StaticFiles(directory=WEB_ROOT / "admin", html=True), name="admin")


def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    """Dependency that resolves currently authenticated user from bearer token."""
    # Pull raw token from Authorization header.
    try:
        token = extract_bearer_token(authorization)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    # Lookup user by hashed token in active sessions.
    user = get_user_by_session_hash(hash_token(token))
    # Missing user means invalid or revoked/expired session.
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    # Return user dict for endpoint dependency injection.
    return user


def _allowed_admin_emails() -> set[str]:
    """Return normalized configured admin email allow-list."""
    return {
        email.strip().lower()
        for email in (settings.admin_emails or "").split(",")
        if email.strip()
    }


def _is_admin_user(current_user: dict) -> bool:
    """Check whether a user belongs to configured admin email set."""
    allowed = _allowed_admin_emails()
    if not allowed:
        return False
    email = str(current_user.get("email") or "").strip().lower()
    return email in allowed


def _resolve_user_plan(current_user: dict) -> str:
    """Resolve effective plan code with admin override."""
    if _is_admin_user(current_user):
        return "admin"

    subscription = get_active_billing_subscription_by_user(int(current_user["user_id"]))
    if not subscription:
        return "free"

    plan = str(subscription.get("plan_code") or "free").strip().lower()
    if plan in {"starter", "pro"}:
        return plan
    return "free"


def _require_plan(current_user: dict, allowed: set[str], denied_detail: str) -> str:
    """Ensure user's effective plan is in allow-list and return the resolved plan."""
    plan = _resolve_user_plan(current_user)
    if plan not in allowed:
        raise HTTPException(status_code=403, detail=denied_detail)
    return plan


def get_admin_user(current_user: dict = Depends(get_current_user)) -> dict:
    """Ensure current authenticated user is in configured admin email allow-list."""
    allowed = _allowed_admin_emails()
    if not allowed:
        raise HTTPException(status_code=503, detail="Admin access is not configured")

    if not _is_admin_user(current_user):
        raise HTTPException(status_code=403, detail="Admin access denied")

    return current_user


@app.on_event("startup")
def startup() -> None:
    """Initialize storage schema/resources when app starts."""
    logger.info("Initializing storage backend")
    try:
        init_storage()
    except Exception:
        logger.exception("Storage initialization failed")
        raise
    logger.info("Storage initialized successfully")


@app.get("/health")
def health() -> dict:
    """Health check endpoint for uptime monitoring."""
    # Return minimal service metadata.
    return {"status": "ok", "service": settings.app_name, "version": settings.app_version}


@app.get("/")
def root() -> RedirectResponse:
    """Default entrypoint redirects to primary landing page."""
    # Keep root URL short and human-friendly.
    return RedirectResponse(url="/v1/")


@app.get("/buy")
def buy_entry() -> RedirectResponse:
    """Canonical entrypoint for buy page."""
    return RedirectResponse(url="/buy/")


@app.get("/api/v1/buy")
def buy_status(plan: str | None = Query(default=None)) -> dict:
    """Return checkout readiness and configured payment link for selected plan."""
    safe_plan = (plan or "").strip().lower() or None
    if safe_plan == "free":
        return {
            "status": "ready",
            "plan": "free",
            "checkout_enabled": False,
            "checkout_url": None,
            "message": "Free plan does not require payment. Create an account to continue.",
        }

    checkout_url = checkout_link_for_plan(safe_plan or "")
    configured = bool(checkout_url)

    if not safe_plan:
        return {
            "status": "ready",
            "plan": None,
            "checkout_enabled": False,
            "checkout_url": None,
            "message": "Select a plan to continue.",
        }

    if safe_plan not in {"starter", "pro"}:
        return {
            "status": "invalid_plan",
            "plan": safe_plan,
            "checkout_enabled": False,
            "checkout_url": None,
            "message": "Unsupported plan selection.",
        }

    return {
        "status": "ready" if configured else "not_configured",
        "message": "Secure checkout link is ready." if configured else "Payment link is not configured yet.",
        "plan": safe_plan,
        "checkout_enabled": configured,
        "checkout_url": checkout_url if configured else None,
    }


@app.get("/api/v1/account/plan", response_model=AccountPlanResponse)
def account_plan(current_user: dict = Depends(get_current_user)) -> AccountPlanResponse:
    """Return effective account plan for feature gating in frontend/backend."""
    return AccountPlanResponse(
        plan_code=_resolve_user_plan(current_user),
        is_admin=_is_admin_user(current_user),
    )


def _resolve_plan_from_payment(tx_ref: str | None, amount: object, currency: object) -> str | None:
    """Resolve plan using tx_ref hint first, then amount/currency fallback."""
    ref = (tx_ref or "").strip().lower()
    if "starter" in ref:
        return "starter"
    if "pro" in ref:
        return "pro"

    try:
        paid_amount = float(amount)
    except (TypeError, ValueError):
        return None

    paid_currency = str(currency or "").strip().upper()
    expected_currency = (settings.billing_currency or "USD").strip().upper()
    if paid_currency and paid_currency != expected_currency:
        return None

    if abs(paid_amount - float(settings.billing_starter_amount)) < 0.01:
        return "starter"
    if abs(paid_amount - float(settings.billing_pro_amount)) < 0.01:
        return "pro"
    return None


@app.post("/api/v1/payments/flutterwave/webhook")
async def flutterwave_webhook(
    request: Request,
    flutterwave_signature: str | None = Header(default=None, alias="flutterwave-signature"),
) -> dict:
    """Receive Flutterwave webhook, verify authenticity, and activate matching subscription."""
    raw_body = await request.body()
    if not is_valid_webhook_signature(raw_body, flutterwave_signature):
        raise HTTPException(status_code=401, detail="Invalid Flutterwave webhook signature")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook payload") from exc

    event_id = str(payload.get("id") or hashlib.sha256(raw_body).hexdigest())
    event_type = str(payload.get("type") or "unknown")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    provider_status = str(data.get("status") or "unknown")
    tx_ref = str(data.get("tx_ref") or data.get("reference") or "").strip() or None

    created = save_payment_event(
        event_id=event_id,
        provider="flutterwave",
        event_type=event_type,
        status=provider_status,
        tx_ref=tx_ref,
        payload=payload,
    )
    if not created:
        return {"status": "ok", "deduplicated": True}

    if event_type != "charge.completed":
        return {"status": "ok", "ignored": event_type}

    transaction_id = str(data.get("id") or "").strip()
    if not transaction_id:
        return {"status": "ok", "ignored": "missing_transaction_id"}

    try:
        verify_response = verify_transaction(transaction_id)
    except Exception:
        logger.exception("Flutterwave verification failed for tx_id=%s", transaction_id)
        raise HTTPException(status_code=502, detail="Failed to verify Flutterwave transaction")

    if str(verify_response.get("status") or "").strip().lower() != "success":
        return {"status": "ok", "ignored": "verification_unsuccessful"}

    verified_data = verify_response.get("data") if isinstance(verify_response.get("data"), dict) else {}
    payment_status = str(verified_data.get("status") or "").strip().lower()
    if payment_status not in {"successful", "succeeded"}:
        return {"status": "ok", "ignored": "payment_not_successful"}

    customer = verified_data.get("customer") if isinstance(verified_data.get("customer"), dict) else {}
    payer_email = str(customer.get("email") or "").strip().lower()
    if not payer_email:
        return {"status": "ok", "pending": "missing_payer_email"}

    user = get_user_by_email(payer_email)
    if not user:
        logger.warning("Flutterwave paid email has no SignalOps user match: %s", payer_email)
        return {"status": "ok", "pending": "user_not_found"}

    plan_code = _resolve_plan_from_payment(
        tx_ref=tx_ref or str(verified_data.get("tx_ref") or "").strip() or None,
        amount=verified_data.get("amount"),
        currency=verified_data.get("currency"),
    )
    if not plan_code:
        return {"status": "ok", "pending": "plan_unresolved"}

    upsert_billing_subscription(
        user_id=user["user_id"],
        provider="flutterwave",
        plan_code=plan_code,
        provider_status="active",
        payer_email=payer_email,
        tx_ref=tx_ref or str(verified_data.get("tx_ref") or "").strip() or None,
        amount=float(verified_data.get("amount") or 0),
        currency=str(verified_data.get("currency") or "").strip().upper() or None,
        raw_payload=verify_response,
    )

    return {"status": "ok", "activated_user_id": user["user_id"], "plan": plan_code}


@app.get("/c/{conversation_id}")
def conversation_entry(conversation_id: str) -> RedirectResponse:
    """Chat-style short URL that opens dashboard at conversation hash route."""
    # Chat-style URL entrypoint. The id is passed into dashboard via hash route.
    return RedirectResponse(url=f"/dashboard/#/c/{conversation_id}")


@app.post("/api/v1/auth/signup", response_model=SignupResponse)
def signup(payload: SignupRequest) -> SignupResponse:
    """Create a new user account."""
    try:
        # Persist new user with normalized email + hashed password.
        created = create_signup(
            full_name=payload.full_name,
            email=str(payload.email),
            company=payload.company,
            password_hash=hash_password(payload.password),
        )
    except DuplicateEmailError as exc:
        logger.warning("Signup rejected for duplicate email: %s", mask_email(str(payload.email)))
        # Unique email conflict returns explicit 409 response.
        raise HTTPException(status_code=409, detail="Email is already registered") from exc

    logger.info("Signup created for email: %s", mask_email(str(created.get("email") or "")))
    # Return typed signup response payload.
    return SignupResponse(**created)


@app.post("/api/v1/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    """Authenticate user credentials and issue bearer token."""
    # Find user by email.
    user = get_user_by_email(str(payload.email))
    # Reject unknown users and invalid password combinations.
    if not user or not verify_password(payload.password, user["password_hash"]):
        logger.warning("Login failed for email: %s", mask_email(str(payload.email)))
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Generate random session token for this login.
    token = secrets.token_urlsafe(36)
    # Store only hashed token in DB session table.
    create_session(user_id=user["user_id"], token_hash=hash_token(token))

    logger.info("Login succeeded for user_id=%s email=%s", user["user_id"], mask_email(str(user["email"])))

    # Return token + public user profile.
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        user=AuthUser(
            user_id=user["user_id"],
            full_name=user["full_name"],
            email=user["email"],
            company=user["company"],
        ),
    )


@app.get("/api/v1/auth/me", response_model=AuthUser)
def me(current_user: dict = Depends(get_current_user)) -> AuthUser:
    """Return currently authenticated user profile."""
    # Dependency already validated the session.
    return AuthUser(**current_user)


@app.post("/api/v1/auth/logout")
def logout(authorization: str | None = Header(default=None)) -> dict:
    """Revoke current session token."""
    # Parse bearer token from Authorization header.
    try:
        token = extract_bearer_token(authorization)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    # Remove token hash from session store.
    revoke_session(hash_token(token))
    logger.info("Logout completed")
    # Return generic success payload.
    return {"status": "ok"}


@app.get("/api/v1/srl/history", response_model=list[AnalysisHistoryItem])
def analysis_history(
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
) -> list[AnalysisHistoryItem]:
    """List recent analyses for the authenticated user."""
    _require_plan(
        current_user,
        {"starter", "pro", "admin"},
        "History is available on Starter and Pro plans.",
    )
    # Fetch user-scoped analysis history.
    rows = list_analyses(user_id=current_user["user_id"], limit=limit)
    # Convert raw rows into response models.
    return [AnalysisHistoryItem(**row) for row in rows]


@app.get("/api/v1/srl/history/{run_id}", response_model=AnalysisResponse)
def analysis_by_id(
    run_id: int,
    current_user: dict = Depends(get_current_user),
) -> AnalysisResponse:
    """Fetch one saved analysis by run ID for current user."""
    _require_plan(
        current_user,
        {"starter", "pro", "admin"},
        "History is available on Starter and Pro plans.",
    )
    # Retrieve analysis payload using user scope.
    payload = get_analysis(run_id=run_id, user_id=current_user["user_id"])
    # Missing payload means not found or not owned by this user.
    if not payload:
        raise HTTPException(status_code=404, detail="Analysis run not found")
    # Return typed analysis response.
    return AnalysisResponse(**payload)


def _run_analysis_from_events(
    *,
    user_id: int,
    segment: str,
    source_file: str,
    events,
    content_hash: str,
) -> AnalysisResponse:
    """Run core analytics pipeline and persist the result."""
    features = generate_feature_snapshot(events)
    windows = compute_comparison_windows(events)
    findings = detect_leaks(features, windows)
    summary, diagnosis = build_report(features, findings)

    response = AnalysisResponse(
        segment=segment,
        summary=summary,
        features=features,
        findings=findings,
        diagnosis=diagnosis,
        source_file=source_file,
        from_cache=False,
    )
    persisted = save_analysis(
        user_id=user_id,
        source_file=source_file,
        segment=segment,
        summary=summary,
        payload=response.model_dump(),
        content_hash=content_hash,
    )
    response.run_id = persisted["run_id"]
    response.created_at = persisted["created_at"]
    return response


def _compute_access_token_expires_at(token_payload: dict) -> str | None:
    """Return ISO UTC expiry timestamp from Shopify token payload when available."""
    expires_in_raw = token_payload.get("expires_in")
    if expires_in_raw is None:
        return None

    try:
        expires_in_seconds = int(expires_in_raw)
    except (TypeError, ValueError):
        return None

    if expires_in_seconds <= 0:
        return None

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
    return expires_at.isoformat()


def _coerce_utc_datetime(value: object) -> datetime | None:
    """Parse DB/API timestamp value into UTC-aware datetime when possible."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    text = str(value).strip()
    if not text:
        return None

    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _needs_token_refresh(connection: dict) -> bool:
    """Decide whether Shopify access token should be refreshed before API calls."""
    expires_at = _coerce_utc_datetime(connection.get("access_token_expires_at"))

    if not expires_at:
        return False

    leeway = max(0, int(settings.shopify_token_refresh_leeway_seconds))
    return datetime.now(timezone.utc) + timedelta(seconds=leeway) >= expires_at


def _run_shopify_monitor_for_connection(connection: dict, segment: str) -> bool:
    """Run one monitor cycle for a single Shopify connection.

    Returns True when a fresh analysis is persisted, else False.
    """
    access_token = str(connection.get("access_token") or "").strip()
    refresh_token = str(connection.get("refresh_token") or "").strip()
    if not access_token:
        raise RuntimeError("Missing Shopify access token. Reconnect your store.")

    # Refresh only when token has refresh metadata and expiry window indicates it is due.
    if refresh_token and _needs_token_refresh(connection):
        refreshed = refresh_offline_access_token(connection["shop_domain"], refresh_token)
        new_access_token = str(refreshed.get("access_token") or "").strip()
        if not new_access_token:
            raise RuntimeError("Shopify token refresh failed: missing access_token")

        new_refresh_token = str(refreshed.get("refresh_token") or "").strip() or refresh_token
        new_expires_at = _compute_access_token_expires_at(refreshed)

        update_shopify_connection_tokens(
            user_id=connection["user_id"],
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            access_token_expires_at=new_expires_at,
        )
        connection["access_token"] = new_access_token
        connection["refresh_token"] = new_refresh_token
        connection["access_token_expires_at"] = new_expires_at
        access_token = new_access_token

    def _fetch_orders_for_connection(token: str):
        return fetch_orders(
            shop_domain=connection["shop_domain"],
            access_token=token,
            updated_at_min=connection.get("last_synced_at"),
        )

    try:
        orders = _fetch_orders_for_connection(access_token)
    except RuntimeError as exc:
        message = str(exc)
        lowered = message.lower()
        if "non-expiring access tokens" in lowered and not refresh_token:
            # One-time migration path for legacy non-expiring offline tokens.
            migrated = migrate_legacy_offline_access_token(connection["shop_domain"], access_token)
            migrated_access_token = str(migrated.get("access_token") or "").strip()
            migrated_refresh_token = str(migrated.get("refresh_token") or "").strip()
            migrated_expires_at = _compute_access_token_expires_at(migrated)
            if not migrated_access_token or not migrated_refresh_token:
                raise RuntimeError(
                    "Shopify token migration failed. Ensure expiring offline tokens are enabled for this app, then reconnect the store."
                ) from exc

            update_shopify_connection_tokens(
                user_id=connection["user_id"],
                access_token=migrated_access_token,
                refresh_token=migrated_refresh_token,
                access_token_expires_at=migrated_expires_at,
            )
            connection["access_token"] = migrated_access_token
            connection["refresh_token"] = migrated_refresh_token
            connection["access_token_expires_at"] = migrated_expires_at
            access_token = migrated_access_token
            refresh_token = migrated_refresh_token
            orders = _fetch_orders_for_connection(access_token)
        elif "non-expiring access tokens" in lowered:
            raise RuntimeError(
                "Shopify returned a legacy non-expiring token. Enable expiring offline tokens for this app in Shopify Partner Dashboard, then disconnect and reconnect this store."
            ) from exc
        else:
            raise

    if not orders:
        save_monitor_run(
            user_id=connection["user_id"],
            shop_domain=connection["shop_domain"],
            segment=segment,
            status="no_data",
            detail={"message": "No new orders returned"},
        )
        return False

    events = normalize_shopify_orders(orders)
    content_hash = hashlib.sha256(json.dumps(orders, sort_keys=True).encode("utf-8")).hexdigest()
    cached = find_analysis_by_hash(
        content_hash=content_hash,
        segment=segment,
        user_id=connection["user_id"],
    )
    if cached:
        mark_shopify_connection_synced(connection["user_id"])
        save_monitor_run(
            user_id=connection["user_id"],
            shop_domain=connection["shop_domain"],
            segment=segment,
            status="cached",
            detail={"run_id": cached.get("run_id")},
        )
        return False

    response = _run_analysis_from_events(
        user_id=connection["user_id"],
        segment=segment,
        source_file=f"shopify:{connection['shop_domain']}",
        events=events,
        content_hash=content_hash,
    )
    mark_shopify_connection_synced(connection["user_id"])
    save_monitor_run(
        user_id=connection["user_id"],
        shop_domain=connection["shop_domain"],
        segment=segment,
        status="ok",
        detail={"run_id": response.run_id, "findings": len(response.findings)},
    )
    return True


@app.post("/api/v1/srl/analyze", response_model=AnalysisResponse)
async def analyze_csv(
    file: UploadFile = File(...),
    segment: str = "shopify-5k-25k",
    current_user: dict = Depends(get_current_user),
) -> AnalysisResponse:
    """Analyze uploaded CSV, detect leaks, and persist result."""
    plan = _resolve_user_plan(current_user)
    if plan == "free":
        existing_runs = list_analyses(user_id=current_user["user_id"], limit=2)
        if len(existing_runs) >= 1:
            raise HTTPException(
                status_code=403,
                detail="Free plan supports one CSV analysis. Upgrade to Starter or Pro for continuous analysis.",
            )

    started_at = time.perf_counter()
    logger.info("Analysis requested by user_id=%s segment=%s file=%s", current_user["user_id"], segment, file.filename)
    # Require a filename to identify uploaded file.
    if not file.filename:
        raise HTTPException(status_code=400, detail="Upload a CSV file")
    # Restrict ingestion to CSV format for current MVP.
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported for MVP ingestion")

    # Read full upload contents into memory.
    raw = await file.read()
    # Reject empty uploads.
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    # Hash file contents to detect duplicate uploads.
    content_hash = hashlib.sha256(raw).hexdigest()
    # Check cache for an existing analysis with same file hash + segment + user.
    cached_payload = find_analysis_by_hash(
        content_hash=content_hash,
        segment=segment,
        user_id=current_user["user_id"],
    )
    # Return cached analysis immediately when available.
    if cached_payload:
        logger.info(
            "Cache hit for user_id=%s file=%s segment=%s",
            current_user["user_id"],
            file.filename,
            segment,
        )
        cached_payload["from_cache"] = True
        # Prefer current filename if upload has one.
        cached_payload["source_file"] = file.filename or cached_payload.get("source_file")
        save_analysis_timing(
            user_id=current_user["user_id"],
            source="csv_cached",
            duration_ms=(time.perf_counter() - started_at) * 1000.0,
        )
        return AnalysisResponse(**cached_payload)

    try:
        # Preferred decode path for UTF-8 CSV files (handles UTF-8 BOM too).
        csv_text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Fallback for files exported in legacy encodings.
        csv_text = raw.decode("latin-1")

    try:
        # Normalize external CSV into canonical event records.
        events = normalize_orders_csv(csv_text=csv_text)
    except CSVNormalizationError as exc:
        logger.warning("CSV normalization failed for file=%s user_id=%s: %s", file.filename, current_user["user_id"], exc)
        # Expose normalization problems as 400 for frontend display.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        response = _run_analysis_from_events(
            user_id=current_user["user_id"],
            source_file=file.filename,
            segment=segment,
            events=events,
            content_hash=content_hash,
        )
    except Exception:
        logger.exception("Failed to persist analysis for user_id=%s file=%s", current_user["user_id"], file.filename)
        raise
    logger.info(
        "Analysis generated for user_id=%s file=%s findings=%s from_cache=%s",
        current_user["user_id"],
        file.filename,
        len(response.findings),
        False,
    )
    save_analysis_timing(
        user_id=current_user["user_id"],
        source="csv_upload",
        duration_ms=(time.perf_counter() - started_at) * 1000.0,
    )
    # Return final analysis payload.
    return response


@app.get("/api/v1/admin/founder-metrics", response_model=FounderPostPackMetricsResponse)
def founder_metrics(admin_user: dict = Depends(get_admin_user)) -> FounderPostPackMetricsResponse:
    """Return founder post-pack metrics for the authenticated admin."""
    _ = admin_user
    payload = get_founder_post_pack_metrics(window_days=7)
    return FounderPostPackMetricsResponse(**payload)


@app.get("/api/v1/admin/feature-timeseries", response_model=AdminFeatureTimeSeriesResponse)
def admin_feature_timeseries(
    days: int = Query(default=30, ge=7, le=180),
    admin_user: dict = Depends(get_admin_user),
) -> AdminFeatureTimeSeriesResponse:
    """Return feature-level time-series points for admin chart cards."""
    _ = admin_user
    points = get_admin_feature_timeseries(window_days=days)
    return AdminFeatureTimeSeriesResponse(
        generated_at=datetime.now(timezone.utc).isoformat(),
        window_days=days,
        points=points,
    )


@app.post("/api/v1/integrations/shopify/connect/start", response_model=ShopifyConnectStartResponse)
def shopify_connect_start(
    payload: ShopifyConnectStartRequest,
    current_user: dict = Depends(get_current_user),
) -> ShopifyConnectStartResponse:
    """Generate Shopify OAuth install URL for current user."""
    _require_plan(
        current_user,
        {"pro", "admin"},
        "Shopify integration is available on Pro plan.",
    )

    if not settings.shopify_api_key or not settings.shopify_api_secret:
        raise HTTPException(status_code=503, detail="Shopify integration is not configured")

    try:
        shop_domain = normalize_shop_domain(payload.shop_domain)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    state = build_oauth_state(current_user["user_id"], shop_domain)
    auth_url = build_install_url(shop_domain, state)
    return ShopifyConnectStartResponse(auth_url=auth_url, shop_domain=shop_domain)


@app.get("/api/v1/integrations/shopify/callback")
def shopify_connect_callback(request: Request):
    """Handle Shopify OAuth callback, validate, and persist store token."""
    query = {key: value for key, value in request.query_params.items()}
    if not verify_callback_hmac(query):
        raise HTTPException(status_code=401, detail="Invalid Shopify callback signature")

    shop = query.get("shop")
    code = query.get("code")
    state = query.get("state")
    if not shop or not code or not state:
        raise HTTPException(status_code=400, detail="Missing required OAuth callback parameters")

    try:
        state_user_id, state_shop_domain = parse_oauth_state(state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    normalized_shop = normalize_shop_domain(shop)
    if normalized_shop != state_shop_domain:
        raise HTTPException(status_code=400, detail="Shop domain mismatch in OAuth callback")

    token_payload = exchange_code_for_token(normalized_shop, code)
    access_token = str(token_payload.get("access_token") or "").strip()
    refresh_token = str(token_payload.get("refresh_token") or "").strip() or None
    access_token_expires_at = _compute_access_token_expires_at(token_payload)
    scope = str(token_payload.get("scope") or "").strip() or None
    if not access_token:
        raise HTTPException(status_code=502, detail="Shopify token exchange failed")

    upsert_shopify_connection(
        user_id=state_user_id,
        shop_domain=normalized_shop,
        access_token=access_token,
        refresh_token=refresh_token,
        access_token_expires_at=access_token_expires_at,
        scope=scope,
    )

    return RedirectResponse(url="/dashboard/?shopify=connected")


@app.get("/api/v1/integrations/shopify/status", response_model=ShopifyConnectionStatusResponse)
def shopify_status(current_user: dict = Depends(get_current_user)) -> ShopifyConnectionStatusResponse:
    """Return current user's Shopify integration status."""
    _require_plan(
        current_user,
        {"pro", "admin"},
        "Shopify integration is available on Pro plan.",
    )

    row = get_shopify_connection_by_user(current_user["user_id"])
    if not row:
        return ShopifyConnectionStatusResponse(connected=False)
    return ShopifyConnectionStatusResponse(
        connected=True,
        shop_domain=row["shop_domain"],
        scope=row["scope"],
        last_synced_at=row["last_synced_at"],
    )


@app.post("/api/v1/integrations/shopify/disconnect")
def shopify_disconnect(current_user: dict = Depends(get_current_user)) -> dict:
    """Disconnect Shopify integration for current user."""
    _require_plan(
        current_user,
        {"pro", "admin"},
        "Shopify integration is available on Pro plan.",
    )

    deactivate_shopify_connection(current_user["user_id"])
    return {"status": "ok"}


@app.post("/api/v1/integrations/shopify/webhook/orders")
async def shopify_orders_webhook(
    request: Request,
    x_shopify_hmac_sha256: str | None = Header(default=None),
) -> dict:
    """Accept Shopify order webhooks and validate signature."""
    body = await request.body()
    if not verify_webhook_hmac(body, x_shopify_hmac_sha256):
        raise HTTPException(status_code=401, detail="Invalid Shopify webhook signature")
    return {"status": "ok"}


@app.post("/api/v1/integrations/shopify/monitor-now", response_model=MonitorRunResponse)
def run_shopify_monitor_now(current_user: dict = Depends(get_current_user)) -> MonitorRunResponse:
    """Run monitor immediately for the authenticated user's connected store."""
    _require_plan(
        current_user,
        {"pro", "admin"},
        "Shopify monitoring is available on Pro plan.",
    )

    segment = "shopify-5k-25k"
    connection = get_shopify_connection_by_user(current_user["user_id"])
    if not connection:
        raise HTTPException(status_code=404, detail="No active Shopify connection found")

    try:
        created = _run_shopify_monitor_for_connection(connection, segment=segment)
    except Exception as exc:
        logger.exception("Shopify monitor-now failed for shop=%s", connection["shop_domain"])
        save_monitor_run(
            user_id=connection["user_id"],
            shop_domain=connection["shop_domain"],
            segment=segment,
            status="error",
            detail={"error": str(exc)},
        )
        detail = str(exc).strip() or "Monitor run failed for connected store"
        raise HTTPException(status_code=502, detail=detail[:500]) from exc

    return MonitorRunResponse(processed_stores=1, triggered_analyses=1 if created else 0)


@app.post("/api/v1/monitor/run/shopify", response_model=MonitorRunResponse)
def run_shopify_monitor(
    x_monitor_token: str | None = Header(default=None),
    limit: int = Query(default=25, ge=1, le=200),
) -> MonitorRunResponse:
    """Run autonomous monitor pass over active Shopify connections."""
    if not settings.monitor_internal_token or x_monitor_token != settings.monitor_internal_token:
        raise HTTPException(status_code=401, detail="Invalid monitor token")

    segment = "shopify-5k-25k"
    processed = 0
    analyses = 0

    for connection in list_active_shopify_connections(limit=limit):
        processed += 1
        try:
            created = _run_shopify_monitor_for_connection(connection, segment=segment)
            if created:
                analyses += 1
        except Exception as exc:
            logger.exception("Shopify monitor failed for shop=%s", connection["shop_domain"])
            save_monitor_run(
                user_id=connection["user_id"],
                shop_domain=connection["shop_domain"],
                segment=segment,
                status="error",
                detail={"error": str(exc)},
            )

    return MonitorRunResponse(processed_stores=processed, triggered_analyses=analyses)


@app.post("/api/v1/maintenance/data-retention/run", response_model=DataRetentionRunResponse)
def run_data_retention_cleanup(x_monitor_token: str | None = Header(default=None)) -> DataRetentionRunResponse:
    """Run data retention cleanup pass over persisted records."""
    if not settings.monitor_internal_token or x_monitor_token != settings.monitor_internal_token:
        raise HTTPException(status_code=401, detail="Invalid monitor token")

    try:
        result = run_data_retention()
    except Exception:
        logger.exception("Data retention cleanup failed")
        raise HTTPException(status_code=500, detail="Data retention cleanup failed")

    return DataRetentionRunResponse(**result)
