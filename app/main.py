# Standard library imports for hashing, logging, timing, tokens, and filesystem paths.
import hashlib
import hmac
import logging
import os
import secrets
import time
from pathlib import Path

# FastAPI primitives for app, request handling, dependency injection, and file uploads.
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
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
    AuthUser,
    AnalysisHistoryItem,
    AnalysisResponse,
    LoginRequest,
    LoginResponse,
    SignupRequest,
    SignupResponse,
)
# Feature engineering helpers for analytics calculations.
from app.services.features import compute_comparison_windows, generate_feature_snapshot
# CSV normalization helper and explicit normalization error type.
from app.services.ingestion import CSVNormalizationError, normalize_orders_csv
# Leak rule engine that generates findings from computed features.
from app.services.leak_engine import detect_leaks
# Persistence layer for users, sessions, analysis history, and caching.
from app.services.persistence import (
    DuplicateEmailError,
    create_signup,
    create_session,
    find_analysis_by_hash,
    get_analysis,
    get_user_by_email,
    get_user_by_session_hash,
    init_storage,
    list_analyses,
    revoke_session,
    save_analysis,
)
# Report builder that converts findings into summary + diagnosis text.
from app.services.report_generator import build_report


if not logging.getLogger().handlers:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

logger = logging.getLogger(__name__)


def _mask_email(value: str | None) -> str:
    """Return a partially masked email string for safe logging."""
    email = (value or "").strip().lower()
    if not email or "@" not in email:
        return "***"

    local, domain = email.split("@", 1)
    masked_local = f"{local[:1]}***" if local else "***"
    if "." in domain:
        host, suffix = domain.rsplit(".", 1)
        masked_host = f"{host[:1]}***" if host else "***"
        masked_domain = f"{masked_host}.{suffix}"
    else:
        masked_domain = f"{domain[:1]}***" if domain else "***"

    return f"{masked_local}@{masked_domain}"


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


def _hash_password(password: str) -> str:
    """Hash a password with PBKDF2-SHA256 and a random salt."""
    # Generate a cryptographic random 16-byte salt.
    salt = os.urandom(16)
    # Derive hash digest using PBKDF2-HMAC-SHA256.
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    # Store as a structured string: scheme$iterations$salt$hash.
    return f"pbkdf2_sha256$120000${salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    """Verify a plain password against stored PBKDF2 hash string."""
    try:
        # Split stored record into expected parts.
        scheme, iterations, salt_hex, digest_hex = stored.split("$", 3)
        # Reject unknown schemes immediately.
        if scheme != "pbkdf2_sha256":
            return False
        # Recompute hash using stored salt/iterations and candidate password.
        check = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        ).hex()
        # Constant-time comparison prevents timing side-channel leaks.
        return hmac.compare_digest(check, digest_hex)
    except Exception:
        # Any parse/hash error means verification failed.
        return False


def _hash_token(token: str) -> str:
    """Hash session token before storage/lookup."""
    # Never store raw tokens in DB; keep only SHA256 hash.
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _extract_bearer_token(authorization: str | None) -> str:
    """Extract and validate Bearer token from Authorization header."""
    # Header is required for protected endpoints.
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization token")
    # Expected format is: "Bearer <token>".
    parts = authorization.strip().split(" ", 1)
    # Reject malformed/missing token values.
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise HTTPException(status_code=401, detail="Invalid authorization format")
    # Return normalized token value.
    return parts[1].strip()


def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    """Dependency that resolves currently authenticated user from bearer token."""
    # Pull raw token from Authorization header.
    token = _extract_bearer_token(authorization)
    # Lookup user by hashed token in active sessions.
    user = get_user_by_session_hash(_hash_token(token))
    # Missing user means invalid or revoked/expired session.
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    # Return user dict for endpoint dependency injection.
    return user


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
            password_hash=_hash_password(payload.password),
        )
    except DuplicateEmailError as exc:
        logger.warning("Signup rejected for duplicate email: %s", _mask_email(str(payload.email)))
        # Unique email conflict returns explicit 409 response.
        raise HTTPException(status_code=409, detail="Email is already registered") from exc

    logger.info("Signup created for email: %s", _mask_email(str(created.get("email") or "")))
    # Return typed signup response payload.
    return SignupResponse(**created)


@app.post("/api/v1/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    """Authenticate user credentials and issue bearer token."""
    # Find user by email.
    user = get_user_by_email(str(payload.email))
    # Reject unknown users and invalid password combinations.
    if not user or not _verify_password(payload.password, user["password_hash"]):
        logger.warning("Login failed for email: %s", _mask_email(str(payload.email)))
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Generate random session token for this login.
    token = secrets.token_urlsafe(36)
    # Store only hashed token in DB session table.
    create_session(user_id=user["user_id"], token_hash=_hash_token(token))

    logger.info("Login succeeded for user_id=%s email=%s", user["user_id"], _mask_email(str(user["email"])))

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
    token = _extract_bearer_token(authorization)
    # Remove token hash from session store.
    revoke_session(_hash_token(token))
    logger.info("Logout completed")
    # Return generic success payload.
    return {"status": "ok"}


@app.get("/api/v1/srl/history", response_model=list[AnalysisHistoryItem])
def analysis_history(
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
) -> list[AnalysisHistoryItem]:
    """List recent analyses for the authenticated user."""
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
    # Retrieve analysis payload using user scope.
    payload = get_analysis(run_id=run_id, user_id=current_user["user_id"])
    # Missing payload means not found or not owned by this user.
    if not payload:
        raise HTTPException(status_code=404, detail="Analysis run not found")
    # Return typed analysis response.
    return AnalysisResponse(**payload)


@app.post("/api/v1/srl/analyze", response_model=AnalysisResponse)
async def analyze_csv(
    file: UploadFile = File(...),
    segment: str = "shopify-5k-25k",
    current_user: dict = Depends(get_current_user),
) -> AnalysisResponse:
    """Analyze uploaded CSV, detect leaks, and persist result."""
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

    # Compute features and comparison windows used by leak rules.
    features = generate_feature_snapshot(events)
    windows = compute_comparison_windows(events)
    # Detect leak findings from features/windows.
    findings = detect_leaks(features, windows)
    # Build user-readable summary and diagnosis sections.
    summary, diagnosis = build_report(features, findings)

    logger.info(
        "Analysis generated for user_id=%s file=%s findings=%s from_cache=%s",
        current_user["user_id"],
        file.filename,
        len(findings),
        False,
    )

    # Construct in-memory response payload.
    response = AnalysisResponse(
        segment=segment,
        summary=summary,
        features=features,
        findings=findings,
        diagnosis=diagnosis,
        source_file=file.filename,
        from_cache=False,
    )

    # Persist analysis for history browsing and future cache hits.
    try:
        persisted = save_analysis(
            user_id=current_user["user_id"],
            source_file=file.filename,
            segment=segment,
            summary=summary,
            payload=response.model_dump(),
            content_hash=content_hash,
        )
    except Exception:
        logger.exception("Failed to persist analysis for user_id=%s file=%s", current_user["user_id"], file.filename)
        raise
    # Attach persistence metadata to response.
    response.run_id = persisted["run_id"]
    response.created_at = persisted["created_at"]
    # Return final analysis payload.
    return response
