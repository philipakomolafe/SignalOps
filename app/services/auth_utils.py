import hashlib
import hmac
import os


def mask_email(value: str | None) -> str:
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


def hash_password(password: str) -> str:
    """Hash a password with PBKDF2-SHA256 and a random salt."""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return f"pbkdf2_sha256$120000${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Verify a plain password against stored PBKDF2 hash string."""
    try:
        scheme, iterations, salt_hex, digest_hex = stored.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        check = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        ).hex()
        return hmac.compare_digest(check, digest_hex)
    except Exception:
        return False


def hash_token(token: str) -> str:
    """Hash session token before storage/lookup."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def extract_bearer_token(authorization: str | None) -> str:
    """Extract and validate Bearer token from Authorization header."""
    if not authorization:
        raise ValueError("Missing authorization token")
    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise ValueError("Invalid authorization format")
    return parts[1].strip()
