# Logging for report summary creation.
import logging
from typing import List, Tuple

from app.models.schemas import DiagnosisBlock, FeatureSnapshot, LeakFinding


logger = logging.getLogger(__name__)


_SEVERITY_RANK = {
    "critical": 3,
    "high": 2,
    "medium": 1,
    "low": 0,
}


def _ordered_findings(findings: List[LeakFinding]) -> List[LeakFinding]:
    return sorted(findings, key=lambda item: _SEVERITY_RANK.get(item.severity.lower(), -1), reverse=True)


def _context_number(finding: LeakFinding, key: str):
    value = (finding.context or {}).get(key)
    return float(value) if isinstance(value, (int, float)) else None


def _build_summary(findings: List[LeakFinding]) -> str:
    critical = sum(1 for item in findings if item.severity.lower() == "critical")
    high = sum(1 for item in findings if item.severity.lower() == "high")
    top = findings[0]
    return (
        f"Detected {len(findings)} potential revenue leak(s): "
        f"{critical} critical, {high} high priority. "
        f"Primary signal this run: {top.title.lower()}."
    )


def _compose_what_changed(findings: List[LeakFinding], features: FeatureSnapshot) -> str:
    parts: List[str] = []
    for item in findings[:3]:
        if item.id == "revenue_velocity_drop":
            wow = _context_number(item, "wow_revenue_change_pct")
            if wow is not None:
                parts.append(f"week-over-week revenue moved {wow:.2f}%")
        elif item.id == "repeat_rate_decline":
            previous_repeat = _context_number(item, "previous_repeat_rate")
            recent_repeat = _context_number(item, "recent_repeat_rate")
            if previous_repeat is not None and recent_repeat is not None:
                parts.append(f"repeat rate dropped from {previous_repeat:.2f}% to {recent_repeat:.2f}%")
        elif item.id == "purchase_interval_expansion":
            previous_interval = _context_number(item, "previous_purchase_interval")
            recent_interval = _context_number(item, "recent_purchase_interval")
            if previous_interval is not None and recent_interval is not None:
                parts.append(
                    f"average purchase interval expanded from {previous_interval:.2f} to {recent_interval:.2f} days"
                )
        elif item.id == "refund_rate_spike":
            refund_rate = _context_number(item, "refund_rate")
            if refund_rate is not None:
                parts.append(f"refund pressure reached {refund_rate:.2f}%")

    if parts:
        return (
            "In this run, "
            + "; ".join(parts)
            + ". These combined shifts indicate measurable revenue leakage risk in the current window."
        )

    wow = features.week_over_week_revenue_change_pct
    wow_text = f"{wow:.2f}%" if wow is not None else "not available"
    return f"Current thresholds are stable (week-over-week revenue change: {wow_text})."


def _compose_likely_why(findings: List[LeakFinding], features: FeatureSnapshot) -> str:
    has_repeat_pressure = any(item.id in {"repeat_rate_decline", "purchase_interval_expansion"} for item in findings)
    has_demand_pressure = any(item.id == "revenue_velocity_drop" for item in findings)
    has_refund_pressure = any(item.id == "refund_rate_spike" for item in findings)

    reasons: List[str] = []
    if has_demand_pressure:
        reasons.append("top-line demand and conversion momentum likely weakened")
    if has_repeat_pressure:
        reasons.append("return-customer behavior is slowing relative to the previous period")
    if has_refund_pressure:
        reasons.append("post-purchase experience issues may be creating avoidable reversals")

    if reasons:
        return "Most likely drivers this run: " + "; ".join(reasons) + "."

    if features.repeat_rate < 15:
        return "No hard-threshold leak fired, but low repeat behavior suggests early retention friction worth monitoring."
    return "No major abnormal pattern crossed alert thresholds in this window."


def _compose_what_to_do(findings: List[LeakFinding]) -> str:
    actions: List[str] = []

    if any(item.id == "revenue_velocity_drop" for item in findings):
        actions.append("Audit top channels and high-value SKUs from the last 14 days to isolate where conversion softened")
    if any(item.id in {"repeat_rate_decline", "purchase_interval_expansion"} for item in findings):
        actions.append("Launch a 7-14 day reactivation flow focused on second-purchase conversion")
    if any(item.id == "refund_rate_spike" for item in findings):
        actions.append("Break refunds down by SKU and reason, then fix the top two operational causes")

    if not actions:
        return "Keep ingesting fresh order data weekly and review trend drift before changing thresholds."

    return "; ".join(actions) + "."


def build_report(features: FeatureSnapshot, findings: List[LeakFinding]) -> Tuple[str, DiagnosisBlock]:
    logger.info("Building report for %s finding(s)", len(findings))
    if findings:
        ordered = _ordered_findings(findings)
        summary = _build_summary(ordered)
        diagnosis = DiagnosisBlock(
            what_changed=_compose_what_changed(ordered, features),
            likely_why=_compose_likely_why(ordered, features),
            what_to_do=_compose_what_to_do(ordered),
        )
        logger.info("Report built with primary finding: %s", ordered[0].id)
        return summary, diagnosis

    wow = features.week_over_week_revenue_change_pct
    wow_text = f"{wow:.2f}%" if wow is not None else "not available"
    summary = (
        "No critical leak detected by current rules. "
        "Continue monitoring weekly velocity, repeat behavior, and refund pressure."
    )
    diagnosis = DiagnosisBlock(
        what_changed=(
            f"Revenue trend is stable under current thresholds (week-over-week change: {wow_text})."
        ),
        likely_why="Customer and purchase pattern variance remains within expected range.",
        what_to_do="Keep feeding fresh order data weekly and tune thresholds as signal quality improves.",
    )
    logger.info("Report built with no critical leak detected")
    return summary, diagnosis
