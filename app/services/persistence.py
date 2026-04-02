# JSON serialization for persisted payload blobs.
import json
# SQLite runtime + DB operations.
import sqlite3
# Path handling for local DB file location.
from pathlib import Path
# Type hints used in repository-like functions.
from typing import Any, Dict, List, Optional

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
            raise RuntimeError("PostgreSQL URL configured but psycopg is not installed")
        return psycopg.connect(_normalize_postgres_url(_database_url()), row_factory=dict_row)

    # Fallback backend: local SQLite file.
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
            _execute(
                connection,
                """
                CREATE INDEX IF NOT EXISTS idx_user_sessions_user
                ON user_sessions (user_id, session_id DESC)
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
        _execute(
            connection,
            """
            CREATE INDEX IF NOT EXISTS idx_user_sessions_user
            ON user_sessions (user_id, session_id DESC)
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
            raise DuplicateEmailError("Email is already registered") from exc
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


def create_session(user_id: int, token_hash: str) -> Dict[str, Any]:
    """Create session record for authenticated user token hash."""
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

    return {
        "session_id": session_id,
        "created_at": str(row["created_at"]) if row else "",
    }


def get_user_by_session_hash(token_hash: str) -> Optional[Dict[str, Any]]:
    """Resolve active session token hash to user profile."""
    with _connect() as connection:
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


def revoke_session(token_hash: str) -> None:
    """Mark active session as revoked for logout."""
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
