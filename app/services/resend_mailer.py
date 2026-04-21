"""Utilities for sending transactional emails through Resend."""

import json
import urllib.error
import urllib.request
from html import escape

from app.configs.settings import settings


def _send_email_via_resend(*, to_email: str, subject: str, html: str, text: str) -> None:
    """Send one email through Resend with shared request configuration."""
    api_key = (settings.resend_api_key or "").strip()
    sender = (settings.resend_from_email or "").strip()
    if not api_key or not sender:
        raise RuntimeError("Resend email service is not configured")

    from_email = f"SignalOps <{sender}>"

    payload = {
        "from": from_email,
        "to": [to_email],
        "subject": subject,
        "html": html,
        "text": text,
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


def send_password_reset_email(*, to_email: str, reset_url: str) -> None:
    """Send password reset email via Resend."""
    _send_email_via_resend(
        to_email=to_email,
        subject="Reset your SignalOps password",
        html=(
            "<p>You requested a password reset for SignalOps.</p>"
            f"<p><a href=\"{reset_url}\">Reset password</a></p>"
            "<p>This link expires soon. If you did not request this, you can ignore this email.</p>"
        ),
        text=(
            "You requested a password reset for SignalOps.\n\n"
            f"Reset password: {reset_url}\n\n"
            "This link expires soon. If you did not request this, ignore this email."
        ),
    )


def _format_pct(value: object) -> str:
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return "N/A"


def _format_currency(value: object) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


def send_weekly_report_email(
    *,
    to_email: str,
    full_name: str,
    summary: dict,
    analysis: dict | None,
    action_feedback: dict | None,
    shop_domain: str | None,
) -> None:
    """Send a weekly SignalOps report email with current store signals and actions."""
    base_url = str(settings.app_public_base_url or "").strip().rstrip("/")
    dashboard_url = f"{base_url}/dashboard/" if base_url else "/dashboard/"
    logo_url = f"{base_url}/assets/logo.png" if base_url else ""

    findings = analysis.get("findings", []) if isinstance(analysis, dict) else []
    top_products = (
        (((analysis or {}).get("features") or {}).get("product_performance") or {}).get("top_products_by_revenue", [])
        if isinstance(analysis, dict)
        else []
    )
    finding_blocks = "".join(
        (
            "<div style=\"border:1px solid #dbe4ef;border-radius:12px;padding:12px 14px;margin:0 0 12px;background:#ffffff;\">"
            f"<div style=\"font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#64748b;\">{escape(str(item.get('severity') or 'medium'))}</div>"
            f"<h3 style=\"margin:6px 0 8px;font-size:16px;line-height:1.25;color:#0f172a;\">{escape(str(item.get('title') or 'Leak detected'))}</h3>"
            f"<p style=\"margin:0 0 8px;font-size:14px;line-height:1.55;color:#334155;\">{escape(str(item.get('what_changed') or ''))}</p>"
            f"<p style=\"margin:0;font-size:14px;line-height:1.55;color:#1e3a5f;\"><strong>Do next:</strong> {escape(str(item.get('what_to_do') or 'Assign an owner and act this week.'))}</p>"
            "</div>"
        )
        for item in findings[:3]
    )
    if not finding_blocks:
        finding_blocks = (
            "<div style=\"border:1px solid #d9e8dd;border-radius:12px;padding:12px 14px;background:#f6fcf8;\">"
            "<h3 style=\"margin:0 0 8px;font-size:16px;color:#0f172a;\">No critical leak triggered</h3>"
            "<p style=\"margin:0;font-size:14px;line-height:1.55;color:#334155;\">Store performance stayed within the current leak thresholds this week. Keep watching repeat rate, refund rate, and week-over-week revenue.</p>"
            "</div>"
        )

    product_blocks = "".join(
        (
            "<tr>"
            f"<td style=\"padding:8px 0;border-bottom:1px solid #e2e8f0;color:#0f172a;\">{escape(str(item.get('title') or item.get('sku') or 'Untitled product'))}</td>"
            f"<td style=\"padding:8px 0;border-bottom:1px solid #e2e8f0;color:#334155;text-align:right;\">{_format_currency(item.get('net_revenue'))}</td>"
            f"<td style=\"padding:8px 0;border-bottom:1px solid #e2e8f0;color:#334155;text-align:right;\">{_format_pct(item.get('refund_rate'))}</td>"
            "</tr>"
        )
        for item in top_products[:5]
    )
    if not product_blocks:
        product_blocks = (
            "<tr><td colspan=\"3\" style=\"padding:8px 0;color:#64748b;\">No product-level performance rows were available in the latest run.</td></tr>"
        )

    latest_action_html = ""
    latest_action_text = ""
    if action_feedback:
        latest_action_html = (
            "<div style=\"border:1px solid #dbe4ef;border-radius:12px;padding:12px 14px;background:#ffffff;\">"
            f"<p style=\"margin:0 0 6px;font-size:14px;color:#334155;\"><strong>Latest action:</strong> {escape(str(action_feedback.get('action_taken') or ''))}</p>"
            f"<p style=\"margin:0 0 6px;font-size:14px;color:#334155;\"><strong>Outcome:</strong> {escape(str(action_feedback.get('self_reported_outcome') or ''))}</p>"
            f"<p style=\"margin:0;font-size:14px;color:#1e3a5f;\"><strong>Impact:</strong> {escape(str(action_feedback.get('impact_label') or 'Pending'))}</p>"
            "</div>"
        )
        latest_action_text = (
            f"Latest action: {action_feedback.get('action_taken') or ''}\n"
            f"Outcome: {action_feedback.get('self_reported_outcome') or ''}\n"
            f"Impact: {action_feedback.get('impact_label') or 'Pending'}\n"
        )

    recipient_name = full_name.strip() or "there"
    store_label = shop_domain.strip() if shop_domain else "your store"
    html = f"""
    <div style="margin:0;background:#f5f7fb;padding:24px 12px;font-family:Arial,sans-serif;">
      <div style="max-width:680px;margin:0 auto;background:#ffffff;border:1px solid #dbe4ef;border-radius:18px;overflow:hidden;">
        <div style="padding:24px 24px 18px;background:linear-gradient(180deg,#f8fbff 0%,#edf4ff 100%);border-bottom:1px solid #dbe4ef;">
          {'<div style="display:inline-block;margin:0 0 14px;border-radius:12px;overflow:hidden;background:#ffffff;border:1px solid #dbe4ef;padding:6px 8px;"><img src="' + logo_url + '" alt="SignalOps" style="height:36px;width:auto;display:block;border-radius:8px;" /></div>' if logo_url else ''}
          <div style="font-size:12px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:#64748b;">Weekly Report</div>
          <h1 style="margin:8px 0 10px;font-size:28px;line-height:1.15;color:#0f172a;">SignalOps weekly leak brief for {escape(store_label)}</h1>
          <p style="margin:0;font-size:15px;line-height:1.6;color:#334155;">Hi {escape(recipient_name)}, here is your weekly store report with the current demand, retention, refund, and product signals.</p>
        </div>
        <div style="padding:24px;">
          <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:0 0 18px;">
            <div style="border:1px solid #dbe4ef;border-radius:12px;padding:12px;background:#fbfdff;"><div style="font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#64748b;">Revenue</div><div style="margin-top:6px;font-size:22px;font-weight:700;color:#0f172a;">{_format_currency(summary.get('total_revenue'))}</div></div>
            <div style="border:1px solid #dbe4ef;border-radius:12px;padding:12px;background:#fbfdff;"><div style="font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#64748b;">Week-over-week revenue</div><div style="margin-top:6px;font-size:22px;font-weight:700;color:#0f172a;">{_format_pct(summary.get('week_over_week_revenue_change_pct'))}</div></div>
            <div style="border:1px solid #dbe4ef;border-radius:12px;padding:12px;background:#fbfdff;"><div style="font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#64748b;">Repeat rate</div><div style="margin-top:6px;font-size:22px;font-weight:700;color:#0f172a;">{_format_pct(summary.get('repeat_rate'))}</div></div>
            <div style="border:1px solid #dbe4ef;border-radius:12px;padding:12px;background:#fbfdff;"><div style="font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#64748b;">Refund rate</div><div style="margin-top:6px;font-size:22px;font-weight:700;color:#0f172a;">{_format_pct(summary.get('refund_rate'))}</div></div>
          </div>

          <h2 style="margin:0 0 12px;font-size:18px;color:#0f172a;">What needs attention</h2>
          {finding_blocks}

          <h2 style="margin:18px 0 12px;font-size:18px;color:#0f172a;">Top products in the latest run</h2>
          <table style="width:100%;border-collapse:collapse;font-size:14px;">
            <thead>
              <tr>
                <th style="text-align:left;padding:0 0 8px;color:#64748b;font-size:11px;letter-spacing:.08em;text-transform:uppercase;">Product</th>
                <th style="text-align:right;padding:0 0 8px;color:#64748b;font-size:11px;letter-spacing:.08em;text-transform:uppercase;">Net revenue</th>
                <th style="text-align:right;padding:0 0 8px;color:#64748b;font-size:11px;letter-spacing:.08em;text-transform:uppercase;">Refund rate</th>
              </tr>
            </thead>
            <tbody>{product_blocks}</tbody>
          </table>

          <h2 style="margin:18px 0 12px;font-size:18px;color:#0f172a;">Latest action record</h2>
          {latest_action_html or '<p style="margin:0;font-size:14px;line-height:1.55;color:#334155;">No action feedback has been logged yet. Use the Action workspace to record what you changed and track impact.</p>'}

          <div style="margin-top:22px;">
            <a href="{escape(dashboard_url)}" style="display:inline-block;border-radius:999px;background:#111827;color:#ffffff;text-decoration:none;padding:11px 18px;font-size:14px;font-weight:700;">Open SignalOps</a>
          </div>
        </div>
      </div>
    </div>
    """

    text = (
        f"SignalOps weekly leak brief for {store_label}\n\n"
        f"Revenue: {_format_currency(summary.get('total_revenue'))}\n"
        f"Week-over-week revenue: {_format_pct(summary.get('week_over_week_revenue_change_pct'))}\n"
        f"Repeat rate: {_format_pct(summary.get('repeat_rate'))}\n"
        f"Refund rate: {_format_pct(summary.get('refund_rate'))}\n\n"
        "What needs attention:\n"
        + (
            "\n".join(
                f"- {item.get('title') or 'Leak detected'}: {item.get('what_to_do') or item.get('what_changed') or ''}"
                for item in findings[:3]
            )
            if findings
            else "- No critical leak triggered this week."
        )
        + "\n\nTop products:\n"
        + (
            "\n".join(
                f"- {item.get('title') or item.get('sku') or 'Untitled product'}: net {_format_currency(item.get('net_revenue'))}, refund {_format_pct(item.get('refund_rate'))}"
                for item in top_products[:5]
            )
            if top_products
            else "- No product-level rows were available in the latest run."
        )
        + "\n\n"
        + (latest_action_text if latest_action_text else "No action feedback has been logged yet.\n")
        + f"\nOpen SignalOps: {dashboard_url}"
    )

    _send_email_via_resend(
        to_email=to_email,
        subject="Your weekly SignalOps report",
        html=html,
        text=text,
    )
