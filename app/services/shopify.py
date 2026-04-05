import base64
import hashlib
import hmac
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from app.configs.settings import settings


logger = logging.getLogger(__name__)


def _shopify_api_version() -> str:
    """Return configured Shopify Admin API version with safe fallback."""
    return (settings.shopify_api_version or "2026-04").strip() or "2026-04"


def _state_secret() -> str:
    return settings.shopify_state_secret or settings.shopify_api_secret


def normalize_shop_domain(shop_domain: str) -> str:
    """Normalize and validate Shopify domain format."""
    domain = (shop_domain or "").strip().lower()
    if domain.startswith("https://"):
        domain = domain[len("https://") :]
    if domain.startswith("http://"):
        domain = domain[len("http://") :]
    domain = domain.strip("/")

    if not domain.endswith(".myshopify.com"):
        raise ValueError("Shop domain must end with .myshopify.com")
    return domain


def build_oauth_state(user_id: int, shop_domain: str) -> str:
    """Build signed short-lived OAuth state value."""
    now = int(time.time())
    payload = f"{user_id}:{shop_domain}:{now}"
    signature = hmac.new(_state_secret().encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    encoded = base64.urlsafe_b64encode(f"{payload}:{signature}".encode("utf-8")).decode("utf-8")
    return encoded.rstrip("=")


def parse_oauth_state(state: str, max_age_seconds: int = 900) -> tuple[int, str]:
    """Validate OAuth state and return user_id + shop domain."""
    padded = state + ("=" * ((4 - len(state) % 4) % 4))
    decoded = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
    user_id_str, shop_domain, timestamp_str, signature = decoded.split(":", 3)

    payload = f"{user_id_str}:{shop_domain}:{timestamp_str}"
    expected = hmac.new(_state_secret().encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise ValueError("Invalid OAuth state signature")

    now = int(time.time())
    issued_at = int(timestamp_str)
    if now - issued_at > max_age_seconds:
        raise ValueError("OAuth state expired")

    return int(user_id_str), normalize_shop_domain(shop_domain)


def build_install_url(shop_domain: str, state: str) -> str:
    """Build Shopify OAuth install URL for a shop."""
    callback_url = f"{settings.app_public_base_url.rstrip('/')}/api/v1/integrations/shopify/callback"
    params = {
        "client_id": settings.shopify_api_key,
        "scope": settings.shopify_scopes,
        "redirect_uri": callback_url,
        "state": state,
    }
    return f"https://{shop_domain}/admin/oauth/authorize?{urllib.parse.urlencode(params)}"


def verify_callback_hmac(query_params: Dict[str, str]) -> bool:
    """Verify HMAC sent by Shopify callback request."""
    hmac_value = query_params.get("hmac", "")
    if not hmac_value:
        return False

    signed_pairs = []
    for key in sorted(query_params.keys()):
        if key in {"hmac", "signature"}:
            continue
        signed_pairs.append(f"{key}={query_params[key]}")
    message = "&".join(signed_pairs)

    digest = hmac.new(
        settings.shopify_api_secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(digest, hmac_value)


def exchange_code_for_token(shop_domain: str, code: str) -> Dict[str, Any]:
    """Exchange temporary OAuth code for a permanent Shopify access token."""
    payload = {
        "client_id": settings.shopify_api_key,
        "client_secret": settings.shopify_api_secret,
        "code": code,
    }
    url = f"https://{shop_domain}/admin/oauth/access_token"
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url=url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)


def fetch_orders(
    shop_domain: str,
    access_token: str,
    updated_at_min: Optional[str] = None,
    limit: int = 250,
) -> List[Dict[str, Any]]:
    """Fetch orders from Shopify Admin API."""
    params = {
        "status": "any",
        "limit": str(max(1, min(limit, 250))),
        "order": "updated_at asc",
    }
    if updated_at_min:
        params["updated_at_min"] = updated_at_min

    query = urllib.parse.urlencode(params)
    url = f"https://{shop_domain}/admin/api/{_shopify_api_version()}/orders.json?{query}"
    request = urllib.request.Request(
        url=url,
        headers={
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = ""
        try:
            if exc.fp is not None:
                error_body = exc.fp.read().decode("utf-8", errors="replace")
        except Exception:
            error_body = ""

        logger.error(
            "Shopify orders fetch failed for shop=%s status=%s reason=%s body=%s",
            shop_domain,
            exc.code,
            exc.reason,
            error_body[:1000],
        )
        raise RuntimeError(
            f"Shopify API error {exc.code} while fetching orders: {error_body or exc.reason}"
        ) from exc

    payload = json.loads(body)
    orders = payload.get("orders", [])
    if not isinstance(orders, list):
        return []
    return orders


def verify_webhook_hmac(body: bytes, header_hmac: Optional[str]) -> bool:
    """Verify Shopify webhook HMAC signature."""
    if not header_hmac:
        return False
    digest = hmac.new(settings.shopify_api_secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, header_hmac)
