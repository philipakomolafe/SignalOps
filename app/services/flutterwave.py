import base64
import hashlib
import hmac
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict

from app.configs.settings import settings


def is_valid_webhook_signature(raw_body: bytes, signature: str | None) -> bool:
    """Validate Flutterwave webhook HMAC signature using configured secret hash."""
    secret = (settings.flutterwave_webhook_secret_hash or "").strip()
    if not secret or not signature:
        return False

    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature.strip())


def verify_transaction(transaction_id: str) -> Dict[str, Any]:
    """Fetch verified transaction details from Flutterwave verify endpoint."""
    tx_id = (transaction_id or "").strip()
    if not tx_id:
        raise RuntimeError("Missing Flutterwave transaction id")

    secret_key = (settings.flutterwave_secret_key or "").strip()
    if not secret_key:
        raise RuntimeError("Flutterwave secret key is not configured")

    base_url = (settings.flutterwave_api_base_url or "https://api.flutterwave.com").rstrip("/")
    url = f"{base_url}/v3/transactions/{urllib.parse.quote(tx_id, safe='')}/verify"
    request = urllib.request.Request(
        url=url,
        headers={
            "Authorization": f"Bearer {secret_key}",
            "Accept": "application/json",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = ""
        try:
            if exc.fp is not None:
                error_body = exc.fp.read().decode("utf-8", errors="replace")
        except Exception:
            error_body = ""
        raise RuntimeError(
            f"Flutterwave verify failed {exc.code}: {error_body or exc.reason}"
        ) from exc

    return json.loads(body)


def checkout_link_for_plan(plan: str) -> str:
    """Return configured hosted payment link for a plan code."""
    normalized = (plan or "").strip().lower()
    if normalized == "starter":
        return (settings.flutterwave_starter_link or "").strip()
    if normalized == "pro":
        return (settings.flutterwave_pro_link or "").strip()
    return ""
