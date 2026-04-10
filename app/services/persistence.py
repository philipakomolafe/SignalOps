# JSON serialization for persisted payload blobs.
import json
from collections import Counter
# SQLite runtime + DB operations.
import sqlite3
# Path handling for local DB file location.
from pathlib import Path
from datetime import datetime, timezone
# Type hints used in repository-like functions.
from typing import Any, Dict, List, Optional

import logging

# App settings source (includes DB path).
from app.configs.settings import settings

try:
    # PostgreSQL driver used when DATABASE_URL points to Aiven/Render Postgres.
    import psycopg  # type: ignore[import-not-found]
    from psycopg import errors as pg_errors  # type: ignore[import-not-found]
    from psycopg.rows import dict_row  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised only when dependency is absent.
    psycopg = None
    pg_errors = None
    dict_row = None


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


class DuplicateEmailError(ValueError):
    """Raised when creating a user with an email that already exists."""

    pass


def _database_url() -> str:
    """Return configured database URL (if any)."""
    return (settings.persistence_database_url or "").strip()


def _is_postgres() -> bool:
    """Detect whether configured backend is PostgreSQL."""
    db_url = _database_url().lower()
    return db_url.startswith("postgres://") or db_url.startswith("postgresql://")


def _db_path() -> Path:
    """Return configured SQLite database path."""
    return Path(settings.persistence_db_path)


def _normalize_postgres_url(db_url: str) -> str:
    """Normalize postgres:// URLs for drivers that prefer postgresql://."""
    if db_url.startswith("postgres://"):
        return "postgresql://" + db_url[len("postgres://") :]
    return db_url


def _connect() -> Any:
    """Create database connection for configured backend."""
    if _is_postgres():
        if psycopg is None:
            logger.error("PostgreSQL URL configured but psycopg is not installed")
            raise RuntimeError("PostgreSQL URL configured but psycopg is not installed")
        logger.debug("Opening PostgreSQL connection")
        return psycopg.connect(_normalize_postgres_url(_database_url()), row_factory=dict_row)

    # Fallback backend: local SQLite file.
    logger.debug("Opening SQLite connection at %s", _db_path())
    connection = sqlite3.connect(_db_path())
    connection.row_factory = sqlite3.Row
    return connection


def _sql(query: str) -> str:
    """Translate parameter placeholders for selected backend."""
    if _is_postgres():
        return query.replace("?", "%s")
    return query


def _execute(connection: Any, query: str, params: tuple[Any, ...] = ()) -> Any:
    """Execute backend-aware SQL with translated placeholders."""
    return connection.execute(_sql(query), params)


def _is_unique_violation(exc: Exception) -> bool:
    """Return True when exception indicates unique-constraint violation."""
    if isinstance(exc, sqlite3.IntegrityError):
        return True
    if pg_errors is not None and isinstance(exc, pg_errors.UniqueViolation):
        return True
    sqlstate = getattr(exc, "sqlstate", None)
    cause_sqlstate = getattr(getattr(exc, "__cause__", None), "sqlstate", None)
    return sqlstate == "23505" or cause_sqlstate == "23505"


def init_storage() -> None:
    """Initialize database schema and indexes (migration-safe)."""
    logger.info("Initializing storage for %s backend", "postgres" if _is_postgres() else "sqlite")
    if not _is_postgres():
        # Ensure parent directory for SQLite DB file exists.
        db_path = _db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)

    with _connect() as connection:
        if _is_postgres():
            _execute(
                connection,
                """
                CREATE TABLE IF NOT EXISTS analysis_runs (
                    run_id BIGSERIAL PRIMARY KEY,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    user_id BIGINT,
                    source_file TEXT NOT NULL,
                    segment TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    content_hash TEXT,
                    payload_json TEXT NOT NULL
                )
                """,
            )
            logger.debug("Ensured PostgreSQL analysis_runs table exists")

            columns = {
                str(row["column_name"])
                for row in _execute(
                    connection,
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'analysis_runs'
                    """,
                ).fetchall()
            }
            if "content_hash" not in columns:
                _execute(connection, "ALTER TABLE analysis_runs ADD COLUMN content_hash TEXT")
            if "user_id" not in columns:
                _execute(connection, "ALTER TABLE analysis_runs ADD COLUMN user_id BIGINT")

            _execute(
                connection,
                """
                CREATE INDEX IF NOT EXISTS idx_analysis_runs_hash_segment
                ON analysis_runs (content_hash, segment, user_id)
                """,
            )
            _execute(
                connection,
                """
                CREATE INDEX IF NOT EXISTS idx_analysis_runs_user_created
                ON analysis_runs (user_id, run_id DESC)
                """,
            )

            _execute(
                connection,
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGSERIAL PRIMARY KEY,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    full_name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    company TEXT,
                    password_hash TEXT NOT NULL
                )
                """,
            )
            logger.debug("Ensured PostgreSQL users table exists")
            _execute(
                connection,
                """
                CREATE TABLE IF NOT EXISTS user_sessions (
                    session_id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    revoked_at TIMESTAMPTZ
                )
                """,
            )
            logger.debug("Ensured PostgreSQL user_sessions table exists")
            _execute(
                connection,
                """
                CREATE INDEX IF NOT EXISTS idx_user_sessions_user
                ON user_sessions (user_id, session_id DESC)
                """,
            )
            _execute(
                connection,
                """
                CREATE TABLE IF NOT EXISTS shopify_connections (
                    connection_id BIGSERIAL PRIMARY KEY,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    user_id BIGINT NOT NULL UNIQUE,
                    shop_domain TEXT NOT NULL UNIQUE,
                    access_token TEXT NOT NULL,
                    refresh_token TEXT,
                    access_token_expires_at TIMESTAMPTZ,
                    scope TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    last_synced_at TIMESTAMPTZ,
                    uninstalled_at TIMESTAMPTZ
                )
                """,
            )
            shopify_columns = {
                str(row["column_name"])
                for row in _execute(
                    connection,
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'shopify_connections'
                    """,
                ).fetchall()
            }
            if "refresh_token" not in shopify_columns:
                _execute(connection, "ALTER TABLE shopify_connections ADD COLUMN refresh_token TEXT")
            if "access_token_expires_at" not in shopify_columns:
                _execute(connection, "ALTER TABLE shopify_connections ADD COLUMN access_token_expires_at TIMESTAMPTZ")
            _execute(
                connection,
                """
                CREATE INDEX IF NOT EXISTS idx_shopify_connections_status
                ON shopify_connections (status, updated_at DESC)
                """,
            )
            _execute(
                connection,
                """
                CREATE TABLE IF NOT EXISTS monitor_runs (
                    monitor_run_id BIGSERIAL PRIMARY KEY,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    user_id BIGINT,
                    shop_domain TEXT,
                    segment TEXT,
                    status TEXT NOT NULL,
                    detail_json TEXT
                )
                """,
            )
            _execute(
                connection,
                """
                CREATE INDEX IF NOT EXISTS idx_monitor_runs_created
                ON monitor_runs (created_at DESC)
                """,
            )
            _execute(
                connection,
                """
                CREATE TABLE IF NOT EXISTS payment_events (
                    event_id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    event_type TEXT,
                    status TEXT,
                    tx_ref TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """,
            )
            _execute(
                connection,
                """
                CREATE INDEX IF NOT EXISTS idx_payment_events_tx_ref
                ON payment_events (tx_ref, created_at DESC)
                """,
            )
            _execute(
                connection,
                """
                CREATE TABLE IF NOT EXISTS analysis_timings (
                    timing_id BIGSERIAL PRIMARY KEY,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    user_id BIGINT,
                    source TEXT,
                    duration_ms REAL NOT NULL
                )
                """,
            )
            _execute(
                connection,
                """
                CREATE INDEX IF NOT EXISTS idx_analysis_timings_created
                ON analysis_timings (created_at DESC)
                """,
            )
            _execute(
                connection,
                """
                CREATE TABLE IF NOT EXISTS billing_subscriptions (
                    subscription_id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL UNIQUE,
                    provider TEXT NOT NULL,
                    plan_code TEXT NOT NULL,
                    provider_status TEXT NOT NULL,
                    payer_email TEXT,
                    tx_ref TEXT,
                    amount REAL,
                    currency TEXT,
                    raw_payload_json TEXT,
                    last_payment_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """,
            )
            _execute(
                connection,
                """
                CREATE INDEX IF NOT EXISTS idx_billing_subscriptions_plan
                ON billing_subscriptions (plan_code, updated_at DESC)
                """,
            )
            connection.commit()
            return

        _execute(
            connection,
            """
            CREATE TABLE IF NOT EXISTS analysis_runs (
                run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                user_id INTEGER,
                source_file TEXT NOT NULL,
                segment TEXT NOT NULL,
                summary TEXT NOT NULL,
                content_hash TEXT,
                payload_json TEXT NOT NULL
            )
            """,
        )
        logger.debug("Ensured SQLite analysis_runs table exists")

        columns = {
            row["name"]
            for row in _execute(connection, "PRAGMA table_info(analysis_runs)").fetchall()
        }
        if "content_hash" not in columns:
            _execute(connection, "ALTER TABLE analysis_runs ADD COLUMN content_hash TEXT")
        if "user_id" not in columns:
            _execute(connection, "ALTER TABLE analysis_runs ADD COLUMN user_id INTEGER")

        _execute(
            connection,
            """
            CREATE INDEX IF NOT EXISTS idx_analysis_runs_hash_segment
            ON analysis_runs (content_hash, segment, user_id)
            """,
        )
        _execute(
            connection,
            """
            CREATE INDEX IF NOT EXISTS idx_analysis_runs_user_created
            ON analysis_runs (user_id, run_id DESC)
            """,
        )

        _execute(
            connection,
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                company TEXT,
                password_hash TEXT NOT NULL
            )
            """,
        )
        logger.debug("Ensured SQLite users table exists")
        _execute(
            connection,
            """
            CREATE TABLE IF NOT EXISTS user_sessions (
                session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                revoked_at TEXT
            )
            """,
        )
        logger.debug("Ensured SQLite user_sessions table exists")
        _execute(
            connection,
            """
            CREATE INDEX IF NOT EXISTS idx_user_sessions_user
            ON user_sessions (user_id, session_id DESC)
            """,
        )
        _execute(
            connection,
            """
            CREATE TABLE IF NOT EXISTS shopify_connections (
                connection_id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                user_id INTEGER NOT NULL UNIQUE,
                shop_domain TEXT NOT NULL UNIQUE,
                access_token TEXT NOT NULL,
                refresh_token TEXT,
                access_token_expires_at TEXT,
                scope TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                last_synced_at TEXT,
                uninstalled_at TEXT
            )
            """,
        )
        shopify_columns = {
            row["name"]
            for row in _execute(connection, "PRAGMA table_info(shopify_connections)").fetchall()
        }
        if "refresh_token" not in shopify_columns:
            _execute(connection, "ALTER TABLE shopify_connections ADD COLUMN refresh_token TEXT")
        if "access_token_expires_at" not in shopify_columns:
            _execute(connection, "ALTER TABLE shopify_connections ADD COLUMN access_token_expires_at TEXT")
        _execute(
            connection,
            """
            CREATE INDEX IF NOT EXISTS idx_shopify_connections_status
            ON shopify_connections (status, updated_at DESC)
            """,
        )
        _execute(
            connection,
            """
            CREATE TABLE IF NOT EXISTS monitor_runs (
                monitor_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                user_id INTEGER,
                shop_domain TEXT,
                segment TEXT,
                status TEXT NOT NULL,
                detail_json TEXT
            )
            """,
        )
        _execute(
            connection,
            """
            CREATE INDEX IF NOT EXISTS idx_monitor_runs_created
            ON monitor_runs (created_at DESC)
            """,
        )
        _execute(
            connection,
            """
            CREATE TABLE IF NOT EXISTS payment_events (
                event_id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                event_type TEXT,
                status TEXT,
                tx_ref TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
        )
        _execute(
            connection,
            """
            CREATE INDEX IF NOT EXISTS idx_payment_events_tx_ref
            ON payment_events (tx_ref, created_at DESC)
            """,
        )
        _execute(
            connection,
            """
            CREATE TABLE IF NOT EXISTS analysis_timings (
                timing_id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                user_id INTEGER,
                source TEXT,
                duration_ms REAL NOT NULL
            )
            """,
        )
        _execute(
            connection,
            """
            CREATE INDEX IF NOT EXISTS idx_analysis_timings_created
            ON analysis_timings (created_at DESC)
            """,
        )
        _execute(
            connection,
            """
            CREATE TABLE IF NOT EXISTS billing_subscriptions (
                subscription_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                provider TEXT NOT NULL,
                plan_code TEXT NOT NULL,
                provider_status TEXT NOT NULL,
                payer_email TEXT,
                tx_ref TEXT,
                amount REAL,
                currency TEXT,
                raw_payload_json TEXT,
                last_payment_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
        )
        _execute(
            connection,
            """
            CREATE INDEX IF NOT EXISTS idx_billing_subscriptions_plan
            ON billing_subscriptions (plan_code, updated_at DESC)
            """,
        )
        connection.commit()


def save_analysis(
    user_id: int,
    source_file: str,
    segment: str,
    summary: str,
    payload: Dict[str, Any],
    content_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Insert analysis run row and return run metadata."""
    logger.info("Saving analysis for user_id=%s segment=%s source_file=%s", user_id, segment, source_file)
    with _connect() as connection:
        payload_json = json.dumps(payload)
        if _is_postgres():
            row = _execute(
                connection,
                """
                INSERT INTO analysis_runs (user_id, source_file, segment, summary, content_hash, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                RETURNING run_id, created_at
                """,
                (user_id, source_file, segment, summary, content_hash, payload_json),
            ).fetchone()
            connection.commit()
            logger.info("Saved PostgreSQL analysis run_id=%s", row["run_id"])
            return {
                "run_id": int(row["run_id"]),
                "created_at": str(row["created_at"]),
            }

        cursor = _execute(
            connection,
            """
            INSERT INTO analysis_runs (user_id, source_file, segment, summary, content_hash, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, source_file, segment, summary, content_hash, payload_json),
        )
        run_id = int(cursor.lastrowid)
        row = _execute(
            connection,
            "SELECT run_id, created_at FROM analysis_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        connection.commit()
        logger.info("Saved SQLite analysis run_id=%s", run_id)

    return {
        "run_id": run_id,
        "created_at": str(row["created_at"]) if row else "",
    }


def list_analyses(user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    """List recent analysis summaries for a user."""
    capped_limit = max(1, min(limit, 200))
    with _connect() as connection:
        rows = _execute(
            connection,
            """
            SELECT run_id, created_at, source_file, segment, summary
            FROM analysis_runs
            WHERE user_id = ?
            ORDER BY run_id DESC
            LIMIT ?
            """,
            (user_id, capped_limit),
        ).fetchall()

    return [
        {
            "run_id": int(row["run_id"]),
            "created_at": str(row["created_at"]),
            "source_file": str(row["source_file"]),
            "segment": str(row["segment"]),
            "summary": str(row["summary"]),
        }
        for row in rows
    ]


def get_analysis(run_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    """Fetch one persisted analysis payload for given user and run id."""
    with _connect() as connection:
        row = _execute(
            connection,
            """
            SELECT run_id, created_at, source_file, payload_json
            FROM analysis_runs
            WHERE run_id = ? AND user_id = ?
            """,
            (run_id, user_id),
        ).fetchone()

    if not row:
        return None

    payload = json.loads(str(row["payload_json"]))
    payload["run_id"] = int(row["run_id"])
    payload["created_at"] = str(row["created_at"])
    payload["source_file"] = str(row["source_file"])
    return payload


def find_analysis_by_hash(content_hash: str, segment: str, user_id: int) -> Optional[Dict[str, Any]]:
    """Find latest analysis by content hash for dedup/caching."""
    with _connect() as connection:
        row = _execute(
            connection,
            """
            SELECT run_id, created_at, source_file, payload_json
            FROM analysis_runs
            WHERE content_hash = ? AND segment = ? AND user_id = ?
            ORDER BY run_id DESC
            LIMIT 1
            """,
            (content_hash, segment, user_id),
        ).fetchone()

    if not row:
        return None

    payload = json.loads(str(row["payload_json"]))
    payload["run_id"] = int(row["run_id"])
    payload["created_at"] = str(row["created_at"])
    payload["source_file"] = str(row["source_file"])
    return payload


def create_signup(
    full_name: str,
    email: str,
    password_hash: str,
    company: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new user account row and return user profile fields."""
    normalized_email = email.strip().lower()
    safe_company = (company or "").strip() or None
    logger.info("Creating signup for email=%s", _mask_email(normalized_email))

    try:
        with _connect() as connection:
            if _is_postgres():
                row = _execute(
                    connection,
                    """
                    INSERT INTO users (full_name, email, company, password_hash)
                    VALUES (?, ?, ?, ?)
                    RETURNING user_id, created_at, full_name, email, company
                    """,
                    (full_name.strip(), normalized_email, safe_company, password_hash),
                ).fetchone()
                connection.commit()
            else:
                cursor = _execute(
                    connection,
                    """
                    INSERT INTO users (full_name, email, company, password_hash)
                    VALUES (?, ?, ?, ?)
                    """,
                    (full_name.strip(), normalized_email, safe_company, password_hash),
                )
                user_id = int(cursor.lastrowid)
                row = _execute(
                    connection,
                    "SELECT user_id, created_at, full_name, email, company FROM users WHERE user_id = ?",
                    (user_id,),
                ).fetchone()
                connection.commit()
    except Exception as exc:
        if _is_unique_violation(exc):
            logger.warning("Duplicate signup attempt for email=%s", _mask_email(normalized_email))
            raise DuplicateEmailError("Email is already registered") from exc
        logger.exception("Signup creation failed for email=%s", _mask_email(normalized_email))
        raise

    if not row:
        return {"email": normalized_email}

    return {
        "user_id": int(row["user_id"]),
        "created_at": str(row["created_at"]),
        "full_name": str(row["full_name"]),
        "email": str(row["email"]),
        "company": str(row["company"]) if row["company"] else None,
    }


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Fetch user row by normalized email, including password hash."""
    normalized_email = email.strip().lower()
    logger.debug("Looking up user by email=%s", _mask_email(normalized_email))
    with _connect() as connection:
        row = _execute(
            connection,
            """
            SELECT user_id, full_name, email, company, password_hash
            FROM users
            WHERE email = ?
            """,
            (normalized_email,),
        ).fetchone()

    if not row:
        return None

    return {
        "user_id": int(row["user_id"]),
        "full_name": str(row["full_name"]),
        "email": str(row["email"]),
        "company": str(row["company"]) if row["company"] else None,
        "password_hash": str(row["password_hash"]),
    }


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Fetch user row by user_id, including email and public profile fields."""
    with _connect() as connection:
        row = _execute(
            connection,
            """
            SELECT user_id, full_name, email, company
            FROM users
            WHERE user_id = ?
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()

    if not row:
        return None

    return {
        "user_id": int(row["user_id"]),
        "full_name": str(row["full_name"]),
        "email": str(row["email"]),
        "company": str(row["company"]) if row["company"] else None,
    }


def create_session(user_id: int, token_hash: str) -> Dict[str, Any]:
    """Create session record for authenticated user token hash."""
    logger.info("Creating session for user_id=%s", user_id)
    with _connect() as connection:
        if _is_postgres():
            row = _execute(
                connection,
                """
                INSERT INTO user_sessions (user_id, token_hash)
                VALUES (?, ?)
                RETURNING session_id, created_at
                """,
                (user_id, token_hash),
            ).fetchone()
            connection.commit()
            logger.info("Created PostgreSQL session_id=%s for user_id=%s", row["session_id"], user_id)
            return {
                "session_id": int(row["session_id"]),
                "created_at": str(row["created_at"]),
            }

        cursor = _execute(
            connection,
            """
            INSERT INTO user_sessions (user_id, token_hash)
            VALUES (?, ?)
            """,
            (user_id, token_hash),
        )
        session_id = int(cursor.lastrowid)
        row = _execute(
            connection,
            "SELECT created_at FROM user_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        connection.commit()
        logger.info("Created SQLite session_id=%s for user_id=%s", session_id, user_id)

    return {
        "session_id": session_id,
        "created_at": str(row["created_at"]) if row else "",
    }


def get_user_by_session_hash(token_hash: str) -> Optional[Dict[str, Any]]:
    """Resolve active session token hash to user profile."""
    with _connect() as connection:
        logger.debug("Resolving session hash to user")
        row = _execute(
            connection,
            """
            SELECT u.user_id, u.full_name, u.email, u.company
            FROM user_sessions s
            JOIN users u ON u.user_id = s.user_id
            WHERE s.token_hash = ? AND s.revoked_at IS NULL
            ORDER BY s.session_id DESC
            LIMIT 1
            """,
            (token_hash,),
        ).fetchone()

    if not row:
        return None

    return {
        "user_id": int(row["user_id"]),
        "full_name": str(row["full_name"]),
        "email": str(row["email"]),
        "company": str(row["company"]) if row["company"] else None,
    }

# revoke token hash.
def revoke_session(token_hash: str) -> None:
    """Mark active session as revoked for logout."""
    logger.info("Revoking session token hash")
    with _connect() as connection:
        _execute(
            connection,
            """
            UPDATE user_sessions
            SET revoked_at = CURRENT_TIMESTAMP
            WHERE token_hash = ? AND revoked_at IS NULL
            """,
            (token_hash,),
        )
        connection.commit()


def upsert_shopify_connection(
    user_id: int,
    shop_domain: str,
    access_token: str,
    refresh_token: Optional[str] = None,
    access_token_expires_at: Optional[str] = None,
    scope: Optional[str] = None,
) -> Dict[str, Any]:
    """Create or update a Shopify store connection for a user."""
    with _connect() as connection:
        if _is_postgres():
            row = _execute(
                connection,
                """
                INSERT INTO shopify_connections (user_id, shop_domain, access_token, refresh_token, access_token_expires_at, scope, status, updated_at, uninstalled_at)
                VALUES (?, ?, ?, ?, ?, ?, 'active', CURRENT_TIMESTAMP, NULL)
                ON CONFLICT (user_id)
                DO UPDATE SET
                    shop_domain = EXCLUDED.shop_domain,
                    access_token = EXCLUDED.access_token,
                    refresh_token = EXCLUDED.refresh_token,
                    access_token_expires_at = EXCLUDED.access_token_expires_at,
                    scope = EXCLUDED.scope,
                    status = 'active',
                    updated_at = CURRENT_TIMESTAMP,
                    uninstalled_at = NULL
                RETURNING user_id, shop_domain, scope, status, last_synced_at, access_token_expires_at
                """,
                (user_id, shop_domain, access_token, refresh_token, access_token_expires_at, scope),
            ).fetchone()
            connection.commit()
        else:
            _execute(
                connection,
                """
                INSERT INTO shopify_connections (user_id, shop_domain, access_token, refresh_token, access_token_expires_at, scope, status, updated_at, uninstalled_at)
                VALUES (?, ?, ?, ?, ?, ?, 'active', CURRENT_TIMESTAMP, NULL)
                ON CONFLICT(user_id)
                DO UPDATE SET
                    shop_domain = excluded.shop_domain,
                    access_token = excluded.access_token,
                    refresh_token = excluded.refresh_token,
                    access_token_expires_at = excluded.access_token_expires_at,
                    scope = excluded.scope,
                    status = 'active',
                    updated_at = CURRENT_TIMESTAMP,
                    uninstalled_at = NULL
                """,
                (user_id, shop_domain, access_token, refresh_token, access_token_expires_at, scope),
            )
            row = _execute(
                connection,
                """
                SELECT user_id, shop_domain, scope, status, last_synced_at, access_token_expires_at
                FROM shopify_connections
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
            connection.commit()

    return {
        "user_id": int(row["user_id"]),
        "shop_domain": str(row["shop_domain"]),
        "scope": str(row["scope"]) if row["scope"] else None,
        "status": str(row["status"]),
        "last_synced_at": str(row["last_synced_at"]) if row["last_synced_at"] else None,
        "access_token_expires_at": str(row["access_token_expires_at"]) if row["access_token_expires_at"] else None,
    }


def update_shopify_connection_tokens(
    user_id: int,
    access_token: str,
    refresh_token: Optional[str],
    access_token_expires_at: Optional[str],
) -> None:
    """Persist refreshed Shopify token credentials for a user."""
    with _connect() as connection:
        _execute(
            connection,
            """
            UPDATE shopify_connections
            SET access_token = ?,
                refresh_token = ?,
                access_token_expires_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND status = 'active'
            """,
            (access_token, refresh_token, access_token_expires_at, user_id),
        )
        connection.commit()


def get_shopify_connection_by_user(user_id: int) -> Optional[Dict[str, Any]]:
    """Return Shopify connection for a user when present."""
    with _connect() as connection:
        row = _execute(
            connection,
            """
            SELECT user_id, shop_domain, access_token, refresh_token, access_token_expires_at, scope, status, last_synced_at
            FROM shopify_connections
            WHERE user_id = ? AND status = 'active'
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()

    if not row:
        return None

    return {
        "user_id": int(row["user_id"]),
        "shop_domain": str(row["shop_domain"]),
        "access_token": str(row["access_token"]),
        "refresh_token": str(row["refresh_token"]) if row["refresh_token"] else None,
        "access_token_expires_at": str(row["access_token_expires_at"]) if row["access_token_expires_at"] else None,
        "scope": str(row["scope"]) if row["scope"] else None,
        "status": str(row["status"]),
        "last_synced_at": str(row["last_synced_at"]) if row["last_synced_at"] else None,
    }


def list_active_shopify_connections(limit: int = 100) -> List[Dict[str, Any]]:
    """List active Shopify connections for scheduled monitoring."""
    capped_limit = max(1, min(limit, 500))
    with _connect() as connection:
        rows = _execute(
            connection,
            """
            SELECT user_id, shop_domain, access_token, refresh_token, access_token_expires_at, scope, status, last_synced_at
            FROM shopify_connections
            WHERE status = 'active'
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (capped_limit,),
        ).fetchall()

    return [
        {
            "user_id": int(row["user_id"]),
            "shop_domain": str(row["shop_domain"]),
            "access_token": str(row["access_token"]),
            "refresh_token": str(row["refresh_token"]) if row["refresh_token"] else None,
            "access_token_expires_at": str(row["access_token_expires_at"]) if row["access_token_expires_at"] else None,
            "scope": str(row["scope"]) if row["scope"] else None,
            "status": str(row["status"]),
            "last_synced_at": str(row["last_synced_at"]) if row["last_synced_at"] else None,
        }
        for row in rows
    ]


def mark_shopify_connection_synced(user_id: int) -> None:
    """Update sync marker after successful monitor run."""
    with _connect() as connection:
        _execute(
            connection,
            """
            UPDATE shopify_connections
            SET last_synced_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND status = 'active'
            """,
            (user_id,),
        )
        connection.commit()


def deactivate_shopify_connection(user_id: int) -> None:
    """Deactivate Shopify integration for a user."""
    with _connect() as connection:
        _execute(
            connection,
            """
            UPDATE shopify_connections
            SET status = 'inactive', updated_at = CURRENT_TIMESTAMP, uninstalled_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
            """,
            (user_id,),
        )
        connection.commit()


def save_monitor_run(
    user_id: int,
    shop_domain: str,
    segment: str,
    status: str,
    detail: Dict[str, Any],
) -> None:
    """Persist monitor execution outcome for observability and support."""
    with _connect() as connection:
        _execute(
            connection,
            """
            INSERT INTO monitor_runs (user_id, shop_domain, segment, status, detail_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, shop_domain, segment, status, json.dumps(detail)),
        )
        connection.commit()


def run_data_retention() -> Dict[str, int]:
    """Delete stale rows according to configured TTL values."""
    analysis_days = max(1, int(settings.retention_analysis_runs_days))
    monitor_days = max(1, int(settings.retention_monitor_runs_days))
    revoked_session_days = max(1, int(settings.retention_revoked_sessions_days))
    inactive_shopify_days = max(1, int(settings.retention_inactive_shopify_days))

    with _connect() as connection:
        if _is_postgres():
            analysis_deleted = int(
                _execute(
                    connection,
                    """
                    DELETE FROM analysis_runs
                    WHERE created_at < (CURRENT_TIMESTAMP - (?::int * INTERVAL '1 day'))
                    """,
                    (analysis_days,),
                ).rowcount
                or 0
            )
            monitor_deleted = int(
                _execute(
                    connection,
                    """
                    DELETE FROM monitor_runs
                    WHERE created_at < (CURRENT_TIMESTAMP - (?::int * INTERVAL '1 day'))
                    """,
                    (monitor_days,),
                ).rowcount
                or 0
            )
            revoked_sessions_deleted = int(
                _execute(
                    connection,
                    """
                    DELETE FROM user_sessions
                    WHERE revoked_at IS NOT NULL
                      AND revoked_at < (CURRENT_TIMESTAMP - (?::int * INTERVAL '1 day'))
                    """,
                    (revoked_session_days,),
                ).rowcount
                or 0
            )
            inactive_connections_deleted = int(
                _execute(
                    connection,
                    """
                    DELETE FROM shopify_connections
                    WHERE status = 'inactive'
                      AND uninstalled_at IS NOT NULL
                      AND uninstalled_at < (CURRENT_TIMESTAMP - (?::int * INTERVAL '1 day'))
                    """,
                    (inactive_shopify_days,),
                ).rowcount
                or 0
            )
            connection.commit()
        else:
            analysis_deleted = int(
                _execute(
                    connection,
                    """
                    DELETE FROM analysis_runs
                    WHERE datetime(created_at) < datetime('now', ?)
                    """,
                    (f"-{analysis_days} days",),
                ).rowcount
                or 0
            )
            monitor_deleted = int(
                _execute(
                    connection,
                    """
                    DELETE FROM monitor_runs
                    WHERE datetime(created_at) < datetime('now', ?)
                    """,
                    (f"-{monitor_days} days",),
                ).rowcount
                or 0
            )
            revoked_sessions_deleted = int(
                _execute(
                    connection,
                    """
                    DELETE FROM user_sessions
                    WHERE revoked_at IS NOT NULL
                      AND datetime(revoked_at) < datetime('now', ?)
                    """,
                    (f"-{revoked_session_days} days",),
                ).rowcount
                or 0
            )
            inactive_connections_deleted = int(
                _execute(
                    connection,
                    """
                    DELETE FROM shopify_connections
                    WHERE status = 'inactive'
                      AND uninstalled_at IS NOT NULL
                      AND datetime(uninstalled_at) < datetime('now', ?)
                    """,
                    (f"-{inactive_shopify_days} days",),
                ).rowcount
                or 0
            )
            connection.commit()

    total_deleted = analysis_deleted + monitor_deleted + revoked_sessions_deleted + inactive_connections_deleted
    logger.info(
        "Data retention cleanup completed total=%s analysis=%s monitor=%s sessions=%s inactive_shopify=%s",
        total_deleted,
        analysis_deleted,
        monitor_deleted,
        revoked_sessions_deleted,
        inactive_connections_deleted,
    )

    return {
        "total_deleted": total_deleted,
        "analysis_runs_deleted": analysis_deleted,
        "monitor_runs_deleted": monitor_deleted,
        "revoked_sessions_deleted": revoked_sessions_deleted,
        "inactive_connections_deleted": inactive_connections_deleted,
    }


def save_payment_event(
    event_id: str,
    provider: str,
    event_type: str,
    status: str,
    tx_ref: Optional[str],
    payload: Dict[str, Any],
) -> bool:
    """Persist webhook event once; return False when duplicate event_id already exists."""
    try:
        with _connect() as connection:
            _execute(
                connection,
                """
                INSERT INTO payment_events (event_id, provider, event_type, status, tx_ref, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    provider,
                    event_type,
                    status,
                    tx_ref,
                    json.dumps(payload),
                ),
            )
            connection.commit()
        return True
    except Exception as exc:
        if _is_unique_violation(exc):
            return False
        raise


def save_analysis_timing(user_id: int, source: str, duration_ms: float) -> None:
    """Persist analysis turnaround timing for trend reporting."""
    with _connect() as connection:
        _execute(
            connection,
            """
            INSERT INTO analysis_timings (user_id, source, duration_ms)
            VALUES (?, ?, ?)
            """,
            (user_id, source, float(duration_ms)),
        )
        connection.commit()


def upsert_billing_subscription(
    user_id: int,
    provider: str,
    plan_code: str,
    provider_status: str,
    payer_email: Optional[str] = None,
    tx_ref: Optional[str] = None,
    amount: Optional[float] = None,
    currency: Optional[str] = None,
    raw_payload: Optional[Dict[str, Any]] = None,
) -> None:
    """Create or update latest billing subscription state for a user."""
    payload_json = json.dumps(raw_payload or {})
    with _connect() as connection:
        if _is_postgres():
            _execute(
                connection,
                """
                INSERT INTO billing_subscriptions (
                    user_id, provider, plan_code, provider_status, payer_email, tx_ref, amount, currency, raw_payload_json, last_payment_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id)
                DO UPDATE SET
                    provider = EXCLUDED.provider,
                    plan_code = EXCLUDED.plan_code,
                    provider_status = EXCLUDED.provider_status,
                    payer_email = EXCLUDED.payer_email,
                    tx_ref = EXCLUDED.tx_ref,
                    amount = EXCLUDED.amount,
                    currency = EXCLUDED.currency,
                    raw_payload_json = EXCLUDED.raw_payload_json,
                    last_payment_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    user_id,
                    provider,
                    plan_code,
                    provider_status,
                    payer_email,
                    tx_ref,
                    amount,
                    currency,
                    payload_json,
                ),
            )
        else:
            _execute(
                connection,
                """
                INSERT INTO billing_subscriptions (
                    user_id, provider, plan_code, provider_status, payer_email, tx_ref, amount, currency, raw_payload_json, last_payment_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id)
                DO UPDATE SET
                    provider = excluded.provider,
                    plan_code = excluded.plan_code,
                    provider_status = excluded.provider_status,
                    payer_email = excluded.payer_email,
                    tx_ref = excluded.tx_ref,
                    amount = excluded.amount,
                    currency = excluded.currency,
                    raw_payload_json = excluded.raw_payload_json,
                    last_payment_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    user_id,
                    provider,
                    plan_code,
                    provider_status,
                    payer_email,
                    tx_ref,
                    amount,
                    currency,
                    payload_json,
                ),
            )
        connection.commit()


def get_active_billing_subscription_by_user(user_id: int) -> Optional[Dict[str, Any]]:
    """Return active billing subscription row for a user when present."""
    with _connect() as connection:
        row = _execute(
            connection,
            """
            SELECT user_id, provider, plan_code, provider_status, payer_email, tx_ref, amount, currency, updated_at
            FROM billing_subscriptions
            WHERE user_id = ? AND lower(provider_status) = 'active'
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()

    if not row:
        return None

    return {
        "user_id": int(row["user_id"]),
        "provider": str(row["provider"]),
        "plan_code": str(row["plan_code"]),
        "provider_status": str(row["provider_status"]),
        "payer_email": str(row["payer_email"]) if row["payer_email"] else None,
        "tx_ref": str(row["tx_ref"]) if row["tx_ref"] else None,
        "amount": float(row["amount"]) if row["amount"] is not None else None,
        "currency": str(row["currency"]) if row["currency"] else None,
        "updated_at": str(row["updated_at"]) if row["updated_at"] else None,
    }


def get_admin_feature_timeseries(window_days: int = 30) -> List[Dict[str, Any]]:
    """Return ordered per-run feature points from persisted analyses for admin charting."""
    where_sql, params = _window_filter_sql("created_at", max(1, int(window_days)))
    with _connect() as connection:
        rows = _execute(
            connection,
            f"""
            SELECT created_at, payload_json
            FROM analysis_runs
            WHERE {where_sql}
            ORDER BY run_id ASC
            """,
            params,
        ).fetchall()

    points: List[Dict[str, Any]] = []
    for row in rows:
        created_at = str(row["created_at"])
        try:
            payload = json.loads(str(row["payload_json"] or "{}"))
        except Exception:
            payload = {}

        features = payload.get("features") if isinstance(payload, dict) else {}
        if not isinstance(features, dict):
            continue

        wow_raw = features.get("week_over_week_revenue_change_pct")
        wow_value: Optional[float]
        if wow_raw is None:
            wow_value = None
        else:
            try:
                wow_value = float(wow_raw)
            except (TypeError, ValueError):
                wow_value = None

        points.append(
            {
                "timestamp": created_at,
                "total_revenue": float(features.get("total_revenue") or 0.0),
                "order_count": int(features.get("order_count") or 0),
                "customer_count": int(features.get("customer_count") or 0),
                "revenue_per_user": float(features.get("revenue_per_user") or 0.0),
                "purchase_frequency": float(features.get("purchase_frequency") or 0.0),
                "repeat_rate": float(features.get("repeat_rate") or 0.0),
                "refund_rate": float(features.get("refund_rate") or 0.0),
                "week_over_week_revenue_change_pct": wow_value,
            }
        )

    return points


def get_user_feature_timeseries(user_id: int, window_days: int = 7) -> List[Dict[str, Any]]:
    """Return ordered per-run feature points for one user over a rolling lookback window."""
    where_sql, params = _window_filter_sql("created_at", max(1, int(window_days)))
    with _connect() as connection:
        rows = _execute(
            connection,
            f"""
            SELECT created_at, payload_json
            FROM analysis_runs
            WHERE user_id = ? AND {where_sql}
            ORDER BY run_id ASC
            """,
            (int(user_id), *params),
        ).fetchall()

    points: List[Dict[str, Any]] = []
    for row in rows:
        created_at = str(row["created_at"])
        try:
            payload = json.loads(str(row["payload_json"] or "{}"))
        except Exception:
            payload = {}

        features = payload.get("features") if isinstance(payload, dict) else {}
        if not isinstance(features, dict):
            continue

        wow_raw = features.get("week_over_week_revenue_change_pct")
        wow_value: Optional[float]
        if wow_raw is None:
            wow_value = None
        else:
            try:
                wow_value = float(wow_raw)
            except (TypeError, ValueError):
                wow_value = None

        points.append(
            {
                "timestamp": created_at,
                "total_revenue": float(features.get("total_revenue") or 0.0),
                "order_count": int(features.get("order_count") or 0),
                "customer_count": int(features.get("customer_count") or 0),
                "revenue_per_user": float(features.get("revenue_per_user") or 0.0),
                "purchase_frequency": float(features.get("purchase_frequency") or 0.0),
                "repeat_rate": float(features.get("repeat_rate") or 0.0),
                "refund_rate": float(features.get("refund_rate") or 0.0),
                "week_over_week_revenue_change_pct": wow_value,
            }
        )

    return points


def _window_filter_sql(column: str, days: int) -> tuple[str, tuple[Any, ...]]:
    """Return backend-specific WHERE snippet + params for N-day lookback."""
    safe_days = max(1, int(days))
    if _is_postgres():
        return f"{column} >= (CURRENT_TIMESTAMP - (?::int * INTERVAL '1 day'))", (safe_days,)
    return f"datetime({column}) >= datetime('now', ?)", (f"-{safe_days} days",)


def get_founder_post_pack_metrics(window_days: int = 7) -> Dict[str, Any]:
    """Aggregate weekly founder-facing metrics for admin reporting."""
    safe_days = max(1, int(window_days))
    generated_at = datetime.now(timezone.utc).isoformat()

    analysis_where, analysis_params = _window_filter_sql("created_at", safe_days)
    monitor_where, monitor_params = _window_filter_sql("created_at", safe_days)
    users_where, users_params = _window_filter_sql("created_at", safe_days)
    payments_where, payments_params = _window_filter_sql("created_at", safe_days)
    timings_where, timings_params = _window_filter_sql("created_at", safe_days)

    with _connect() as connection:
        analyses_7d_row = _execute(
            connection,
            f"SELECT COUNT(*) AS total FROM analysis_runs WHERE {analysis_where}",
            analysis_params,
        ).fetchone()
        active_users_7d_row = _execute(
            connection,
            f"SELECT COUNT(DISTINCT user_id) AS total FROM analysis_runs WHERE {analysis_where}",
            analysis_params,
        ).fetchone()

        latest_analysis_row = _execute(
            connection,
            """
            SELECT run_id, created_at, payload_json
            FROM analysis_runs
            ORDER BY run_id DESC
            LIMIT 1
            """,
        ).fetchone()

        if _is_postgres():
            turnaround_rows = _execute(
                connection,
                f"""
                SELECT to_char(date_trunc('day', created_at), 'YYYY-MM-DD') AS day, AVG(duration_ms) AS avg_duration_ms
                FROM analysis_timings
                WHERE {timings_where}
                GROUP BY 1
                ORDER BY 1 ASC
                """,
                timings_params,
            ).fetchall()
        else:
            turnaround_rows = _execute(
                connection,
                f"""
                SELECT date(created_at) AS day, AVG(duration_ms) AS avg_duration_ms
                FROM analysis_timings
                WHERE {timings_where}
                GROUP BY date(created_at)
                ORDER BY date(created_at) ASC
                """,
                timings_params,
            ).fetchall()

        monitor_total_row = _execute(
            connection,
            f"SELECT COUNT(*) AS total FROM monitor_runs WHERE {monitor_where}",
            monitor_params,
        ).fetchone()
        monitor_status_rows = _execute(
            connection,
            f"SELECT status, COUNT(*) AS total FROM monitor_runs WHERE {monitor_where} GROUP BY status",
            monitor_params,
        ).fetchall()
        monitor_error_rows = _execute(
            connection,
            f"SELECT detail_json FROM monitor_runs WHERE {monitor_where} AND status = 'error'",
            monitor_params,
        ).fetchall()

        signups_row = _execute(
            connection,
            f"SELECT COUNT(*) AS total FROM users WHERE {users_where}",
            users_params,
        ).fetchone()
        plans_rows = _execute(
            connection,
            """
            SELECT plan_code, COUNT(*) AS total
            FROM billing_subscriptions
            WHERE provider_status = 'active'
            GROUP BY plan_code
            ORDER BY total DESC
            """,
        ).fetchall()
        payment_success_row = _execute(
            connection,
            f"""
            SELECT COUNT(*) AS total
            FROM payment_events
            WHERE {payments_where}
              AND event_type = 'charge.completed'
              AND lower(COALESCE(status, '')) IN ('success', 'successful', 'succeeded')
            """,
            payments_params,
        ).fetchone()

    features = {}
    based_on_run_id = None
    based_on_created_at = None
    if latest_analysis_row:
        based_on_run_id = int(latest_analysis_row["run_id"])
        based_on_created_at = str(latest_analysis_row["created_at"])
        try:
            payload = json.loads(str(latest_analysis_row["payload_json"]))
            features = payload.get("features") if isinstance(payload, dict) else {}
        except Exception:
            features = {}

    status_map = {str(row["status"]): int(row["total"]) for row in monitor_status_rows}
    monitor_total = int(monitor_total_row["total"] or 0) if monitor_total_row else 0
    monitor_success = int(status_map.get("ok", 0) + status_map.get("cached", 0))
    monitor_error = int(status_map.get("error", 0))
    success_rate = round((monitor_success / monitor_total) * 100.0, 2) if monitor_total else 0.0

    error_categories: Counter[str] = Counter()
    for row in monitor_error_rows:
        detail_text = ""
        try:
            parsed = json.loads(str(row["detail_json"] or "{}"))
            detail_text = str(parsed.get("error") or "").strip()
        except Exception:
            detail_text = ""
        if not detail_text:
            detail_text = "unknown_error"
        category = detail_text.split(":", 1)[0].strip().lower().replace(" ", "_")
        error_categories[category or "unknown_error"] += 1

    turnaround_trend = [
        {
            "day": str(row["day"]),
            "avg_duration_ms": round(float(row["avg_duration_ms"] or 0.0), 2),
        }
        for row in turnaround_rows
    ]

    return {
        "generated_at": generated_at,
        "window_days": safe_days,
        "product_impact": {
            "total_revenue_analyzed": round(float(features.get("total_revenue") or 0.0), 2),
            "repeat_rate": round(float(features.get("repeat_rate") or 0.0), 2),
            "refund_rate": round(float(features.get("refund_rate") or 0.0), 2),
            "week_over_week_revenue_change_pct": (
                round(float(features.get("week_over_week_revenue_change_pct")), 2)
                if features.get("week_over_week_revenue_change_pct") is not None
                else None
            ),
            "based_on_run_id": based_on_run_id,
            "based_on_created_at": based_on_created_at,
        },
        "usage_velocity": {
            "analyses_run_7d": int(analyses_7d_row["total"] or 0) if analyses_7d_row else 0,
            "active_users_7d": int(active_users_7d_row["total"] or 0) if active_users_7d_row else 0,
            "csv_to_insight_turnaround_trend": turnaround_trend,
        },
        "monitoring_reliability": {
            "monitor_runs_7d": monitor_total,
            "success_rate_pct": success_rate,
            "error_count_7d": monitor_error,
            "top_error_category": error_categories.most_common(1)[0][0] if error_categories else None,
        },
        "commercial_traction": {
            "new_signups_7d": int(signups_row["total"] or 0) if signups_row else 0,
            "active_subscriptions_by_plan": [
                {
                    "plan_code": str(row["plan_code"]),
                    "total": int(row["total"]),
                }
                for row in plans_rows
            ],
            "payment_success_events_7d": int(payment_success_row["total"] or 0) if payment_success_row else 0,
        },
    }


