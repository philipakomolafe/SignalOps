"""Utilities for sending transactional emails through Resend."""

import json
import urllib.error
import urllib.request

from app.configs.settings import settings


def send_password_reset_email(*, to_email: str, reset_url: str) -> None:
    """Send password reset email via Resend."""
    api_key = (settings.resend_api_key or "").strip()
    from_email = (settings.resend_from_email or "").strip()
    if not api_key or not from_email:
        raise RuntimeError("Resend email service is not configured")

    payload = {
        "from": from_email,
        "to": [to_email],
        "subject": "Reset your SignalOps password",
        "html": (
            "<p>You requested a password reset for SignalOps.</p>"
            f"<p><a href=\"{reset_url}\">Reset password</a></p>"
            "<p>This link expires soon. If you did not request this, you can ignore this email.</p>"
        ),
        "text": (
            "You requested a password reset for SignalOps.\n\n"
            f"Reset password: {reset_url}\n\n"
            "This link expires soon. If you did not request this, ignore this email."
        ),
    }

    public_base = (settings.app_public_base_url).strip().rstrip("/")
    user_agent = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    request = urllib.request.Request(
        url="https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": public_base,
            "Referer": f"{public_base}/",
            "User-Agent": user_agent,
        },
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status < 200 or response.status >= 300:
                raise RuntimeError("Failed to send password reset email")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            if exc.fp is not None:
                detail = exc.fp.read().decode("utf-8", errors="replace")
        except Exception:
            detail = ""
        raise RuntimeError(f"Resend email failed {exc.code}: {detail or exc.reason}") from exc
