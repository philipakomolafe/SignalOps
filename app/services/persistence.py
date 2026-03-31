# JSON serialization for persisted payload blobs.
import json
# SQLite runtime + DB operations.
import sqlite3
# Path handling for DB file location.
from pathlib import Path
# Type hints used in repository-like functions.
from typing import Any, Dict, List, Optional

# App settings source (includes DB path).
from app.configs.settings import settings


def _db_path() -> Path:
    """Return configured SQLite database path."""
    return Path(settings.persistence_db_path)


def _connect() -> sqlite3.Connection:
    """Create SQLite connection with row factory enabled."""
    # Open connection to configured DB file.
    connection = sqlite3.connect(_db_path())
    # Return query rows as dict-like sqlite3.Row objects.
    connection.row_factory = sqlite3.Row
    return connection


def init_storage() -> None:
    """Initialize database schema and indexes (migration-safe)."""
    # Ensure parent directory for DB file exists.
    db_path = _db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Run schema setup and migration checks in one transaction scope.
    with _connect() as connection:
        # Main analysis history table.
        connection.execute(
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
            """
        )

        # Migration-safe column creation for older DB files.
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(analysis_runs)").fetchall()
        }
        # Add missing content_hash column if DB predates caching feature.
        if "content_hash" not in columns:
            connection.execute("ALTER TABLE analysis_runs ADD COLUMN content_hash TEXT")
        # Add missing user_id column if DB predates auth/user scoping.
        if "user_id" not in columns:
            connection.execute("ALTER TABLE analysis_runs ADD COLUMN user_id INTEGER")

        # Index used by dedup cache lookup (hash + segment + user).
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_analysis_runs_hash_segment
            ON analysis_runs (content_hash, segment, user_id)
            """
        )
        # Index used by history listing (latest first per user).
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_analysis_runs_user_created
            ON analysis_runs (user_id, run_id DESC)
            """
        )

        # User account table.
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                company TEXT,
                password_hash TEXT NOT NULL
            )
            """
        )

        # Session token table (stores token hashes, not raw tokens).
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_sessions (
                session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                revoked_at TEXT
            )
            """
        )
        # Session lookup/index by user.
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_user_sessions_user
            ON user_sessions (user_id, session_id DESC)
            """
        )
        # Persist schema/index changes.
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
    # Insert new analysis record.
    with _connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO analysis_runs (user_id, source_file, segment, summary, content_hash, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, source_file, segment, summary, content_hash, json.dumps(payload)),
        )
        # Capture generated run id.
        run_id = int(cursor.lastrowid)
        # Fetch creation timestamp for response metadata.
        row = connection.execute(
            "SELECT run_id, created_at FROM analysis_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        # Commit insert.
        connection.commit()

    # Extract created_at safely.
    created_at = str(row["created_at"]) if row else ""
    # Return metadata used by API response.
    return {"run_id": run_id, "created_at": created_at}


def list_analyses(user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    """List recent analysis summaries for a user."""
    # Enforce sensible limit bounds.
    capped_limit = max(1, min(limit, 200))
    with _connect() as connection:
        # Query latest analysis rows for the user.
        rows = connection.execute(
            """
            SELECT run_id, created_at, source_file, segment, summary
            FROM analysis_runs
            WHERE user_id = ?
            ORDER BY run_id DESC
            LIMIT ?
            """,
            (user_id, capped_limit),
        ).fetchall()

    # Convert row objects to plain dictionaries for response model construction.
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
        # User-scoped lookup prevents cross-user access.
        row = connection.execute(
            """
            SELECT run_id, created_at, source_file, payload_json
            FROM analysis_runs
            WHERE run_id = ? AND user_id = ?
            """,
            (run_id, user_id),
        ).fetchone()

    # Missing row means no matching user-owned analysis.
    if not row:
        return None

    # Deserialize stored payload and enrich with run metadata.
    payload = json.loads(str(row["payload_json"]))
    payload["run_id"] = int(row["run_id"])
    payload["created_at"] = str(row["created_at"])
    payload["source_file"] = str(row["source_file"])
    return payload


def find_analysis_by_hash(content_hash: str, segment: str, user_id: int) -> Optional[Dict[str, Any]]:
    """Find latest analysis by content hash for dedup/caching."""
    with _connect() as connection:
        # Match by hash + segment + user and get most recent run.
        row = connection.execute(
            """
            SELECT run_id, created_at, source_file, payload_json
            FROM analysis_runs
            WHERE content_hash = ? AND segment = ? AND user_id = ?
            ORDER BY run_id DESC
            LIMIT 1
            """,
            (content_hash, segment, user_id),
        ).fetchone()

    # No cache hit found.
    if not row:
        return None

    # Deserialize payload and attach metadata.
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
    # Normalize email for uniqueness/lookup consistency.
    normalized_email = email.strip().lower()
    with _connect() as connection:
        # Insert user account with optional company.
        cursor = connection.execute(
            """
            INSERT INTO users (full_name, email, company, password_hash)
            VALUES (?, ?, ?, ?)
            """,
            (full_name.strip(), normalized_email, (company or "").strip() or None, password_hash),
        )
        # Capture generated user id.
        user_id = int(cursor.lastrowid)
        # Return canonical row from database.
        row = connection.execute(
            "SELECT user_id, created_at, full_name, email, company FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        # Commit insert.
        connection.commit()

    # Fallback return when row fetch unexpectedly fails.
    if not row:
        return {"user_id": user_id, "email": normalized_email}

    # Return normalized user profile payload.
    return {
        "user_id": int(row["user_id"]),
        "created_at": str(row["created_at"]),
        "full_name": str(row["full_name"]),
        "email": str(row["email"]),
        "company": str(row["company"]) if row["company"] else None,
    }


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Fetch user row by normalized email, including password hash."""
    # Normalize for consistent lookup.
    normalized_email = email.strip().lower()
    with _connect() as connection:
        # Fetch auth-relevant columns.
        row = connection.execute(
            """
            SELECT user_id, full_name, email, company, password_hash
            FROM users
            WHERE email = ?
            """,
            (normalized_email,),
        ).fetchone()

    # No matching user.
    if not row:
        return None

    # Return user dict used by auth layer.
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
        # Insert token hash as new active session.
        cursor = connection.execute(
            """
            INSERT INTO user_sessions (user_id, token_hash)
            VALUES (?, ?)
            """,
            (user_id, token_hash),
        )
        # Capture generated session id.
        session_id = int(cursor.lastrowid)
        # Fetch creation timestamp.
        row = connection.execute(
            "SELECT created_at FROM user_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        # Commit insert.
        connection.commit()

    # Return session metadata.
    return {
        "session_id": session_id,
        "created_at": str(row["created_at"]) if row else "",
    }


def get_user_by_session_hash(token_hash: str) -> Optional[Dict[str, Any]]:
    """Resolve active session token hash to user profile."""
    with _connect() as connection:
        # Join sessions to users; only non-revoked sessions are valid.
        row = connection.execute(
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

    # Session missing/expired/revoked.
    if not row:
        return None

    # Return profile fields used as current_user context.
    return {
        "user_id": int(row["user_id"]),
        "full_name": str(row["full_name"]),
        "email": str(row["email"]),
        "company": str(row["company"]) if row["company"] else None,
    }


def revoke_session(token_hash: str) -> None:
    """Mark active session as revoked for logout."""
    with _connect() as connection:
        # Soft-revoke matching active token.
        connection.execute(
            """
            UPDATE user_sessions
            SET revoked_at = CURRENT_TIMESTAMP
            WHERE token_hash = ? AND revoked_at IS NULL
            """,
            (token_hash,),
        )
        # Persist revocation update.
        connection.commit()
