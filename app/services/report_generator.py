# Logging for report summary creation.
import logging
from typing import Dict, List, Tuple

from app.models.schemas import DiagnosisBlock, FeatureSnapshot, LeakFinding


logger = logging.getLogger(__name__)


_SEVERITY_RANK = {
    "critical": 3,
    "high": 2,
    "medium": 1,
    "low": 0,
}

_LENS_ORDER = ("customer", "product", "store")
_LENS_LABEL = {
    "customer": "Customer",
    "product": "Product",
    "store": "Store",
}


def _ordered_findings(findings: List[LeakFinding]) -> List[LeakFinding]:
    return sorted(findings, key=lambda item: _SEVERITY_RANK.get(item.severity.lower(), -1), reverse=True)


def _context_number(finding: LeakFinding, key: str):
    value = (finding.context or {}).get(key)
    return float(value) if isinstance(value, (int, float)) else None


def _lens_for_finding(finding: LeakFinding) -> str:
    if finding.id in {"repeat_rate_decline", "purchase_interval_expansion"}:
        return "customer"
    if finding.id == "refund_rate_spike":
        return "product"
    return "store"


def _build_summary(findings: List[LeakFinding]) -> str:
    critical = sum(1 for item in findings if item.severity.lower() == "critical")
    high = sum(1 for item in findings if item.severity.lower() == "high")
    by_lens = {_lens_for_finding(item) for item in findings}
    return (
        "Decision-ready report: "
        f"{len(findings)} detection(s), {critical} critical, {high} high. "
        f"Impacted lenses: {', '.join(sorted(by_lens))}."
    )


def _group_findings_by_lens(findings: List[LeakFinding]) -> Dict[str, List[LeakFinding]]:
    grouped: Dict[str, List[LeakFinding]] = {lens: [] for lens in _LENS_ORDER}
    for finding in findings:
        grouped[_lens_for_finding(finding)].append(finding)
    return grouped


def _detection_sentence(finding: LeakFinding) -> str:
    if finding.id == "revenue_velocity_drop":
        wow = _context_number(finding, "wow_revenue_change_pct")
        if wow is not None:
            return f"Revenue velocity is down {abs(wow):.2f}% week-over-week."
    if finding.id == "repeat_rate_decline":
        previous_repeat = _context_number(finding, "previous_repeat_rate")
        recent_repeat = _context_number(finding, "recent_repeat_rate")
        if previous_repeat is not None and recent_repeat is not None:
            return (
                "Repeat conversion dropped from "
                f"{previous_repeat:.2f}% to {recent_repeat:.2f}% in the recent window."
            )
    if finding.id == "purchase_interval_expansion":
        previous_interval = _context_number(finding, "previous_purchase_interval")
        recent_interval = _context_number(finding, "recent_purchase_interval")
        if previous_interval is not None and recent_interval is not None:
            return (
                "Time between purchases expanded from "
                f"{previous_interval:.2f} to {recent_interval:.2f} days."
            )
    if finding.id == "refund_rate_spike":
        refund_rate = _context_number(finding, "refund_rate")
        if refund_rate is not None:
            return f"Refund pressure is elevated at {refund_rate:.2f}% of gross revenue."
    return finding.what_changed


def _decision_sentence(finding: LeakFinding) -> str:
    if finding.id == "revenue_velocity_drop":
        return "Decision: Reallocate spend to top-converting channels and pause weak campaign cohorts this week."
    if finding.id == "repeat_rate_decline":
        return "Decision: Launch a second-order recovery flow for first-time buyers in the next 7-14 days."
    if finding.id == "purchase_interval_expansion":
        return "Decision: Move reorder nudges earlier and test a time-bound reorder incentive immediately."
    if finding.id == "refund_rate_spike":
        return "Decision: Prioritize fixing the top refund-driving SKUs before scaling paid acquisition."
    return "Decision: Assign an owner and run a 7-day experiment to reverse this signal."


def _top_product_label(features: FeatureSnapshot, ranking: str = "revenue") -> str | None:
    product_metrics = features.product_performance
    items = (
        product_metrics.top_products_by_revenue
        if ranking == "revenue"
        else product_metrics.top_products_by_refund_rate
    )
    if not items:
        return None
    top = items[0]
    return top.title or top.sku or top.product_id or top.variant_id


def _compose_lens_detection(findings: List[LeakFinding], lens: str, features: FeatureSnapshot) -> str:
    if not findings:
        if lens == "product":
            top_revenue = _top_product_label(features, "revenue")
            top_refund = _top_product_label(features, "refund")
            if features.product_performance.products_analyzed:
                parts = []
                if top_revenue:
                    parts.append(f"Top net revenue is concentrated in {top_revenue}")
                if top_refund:
                    parts.append(f"highest refund pressure sits in {top_refund}")
                if parts:
                    return "Product signals are available: " + "; ".join(parts) + "."
            return "No direct product-level anomaly detected from available product signals."
        return "No critical anomaly detected in this lens for the current window."
    top = findings[0]
    return _detection_sentence(top)


def _compose_lens_decision(findings: List[LeakFinding], lens: str, features: FeatureSnapshot) -> str:
    if not findings:
        if lens == "product":
            top_refund = _top_product_label(features, "refund")
            if top_refund:
                return f"Decision: Monitor {top_refund} closely and keep refund reasons segmented by SKU."
            return "Decision: Keep product risk under watch and monitor top SKUs weekly."
        return "Decision: Keep current plan unchanged and continue weekly monitoring."
    return _decision_sentence(findings[0])


def _compose_what_changed(findings: List[LeakFinding], features: FeatureSnapshot) -> str:
    grouped = _group_findings_by_lens(findings)
    lines = ["A. Detection"]
    for lens in _LENS_ORDER:
        lines.append(f"{_LENS_LABEL[lens]}: {_compose_lens_detection(grouped[lens], lens, features)}")
    return "\n".join(lines)


def _compose_likely_why(findings: List[LeakFinding], features: FeatureSnapshot) -> str:
    has_repeat_pressure = any(item.id in {"repeat_rate_decline", "purchase_interval_expansion"} for item in findings)
    has_demand_pressure = any(item.id == "revenue_velocity_drop" for item in findings)
    has_refund_pressure = any(item.id == "refund_rate_spike" for item in findings)

    reasons: List[str] = []
    if has_demand_pressure:
        reasons.append("store demand and conversion momentum weakened")
    if has_repeat_pressure:
        reasons.append("customer return behavior decelerated")
    if has_refund_pressure:
        reasons.append("product or expectation mismatch is driving reversals")

    if reasons:
        return "Why this matters: " + "; ".join(reasons) + "."

    if features.repeat_rate < 15:
        return "Why this matters: retention is soft even without a threshold breach, so customer risk is building."
    return "Why this matters: no major pattern crossed thresholds in this window."


def _compose_what_to_do(findings: List[LeakFinding], features: FeatureSnapshot) -> str:
    grouped = _group_findings_by_lens(findings)
    lines = ["B. Decision"]
    for lens in _LENS_ORDER:
        lines.append(f"{_LENS_LABEL[lens]}: {_compose_lens_decision(grouped[lens], lens, features)}")
    return "\n".join(lines)


def _compose_what_to_watch_next(findings: List[LeakFinding]) -> str:
    watches: List[str] = [
        "Customer: repeat rate and time-to-second-purchase",
        "Product: refund rate by top SKUs",
        "Store: week-over-week revenue and order count",
    ]
    if not findings:
        return "Over the next 7 days, keep baseline watch on " + "; ".join(watches) + "."
    return "Over the next 7 days, validate decisions using " + "; ".join(watches) + "."


def build_report(features: FeatureSnapshot, findings: List[LeakFinding]) -> Tuple[str, DiagnosisBlock]:
    logger.info("Building report for %s finding(s)", len(findings))
    if findings:
        ordered = _ordered_findings(findings)
        summary = _build_summary(ordered)
        diagnosis = DiagnosisBlock(
            what_changed=_compose_what_changed(ordered, features),
            likely_why=_compose_likely_why(ordered, features),
            what_to_do=_compose_what_to_do(ordered, features),
            what_to_watch_next=_compose_what_to_watch_next(ordered),
        )
        logger.info("Report built with primary finding: %s", ordered[0].id)
        return summary, diagnosis

    wow = features.week_over_week_revenue_change_pct
    wow_text = f"{wow:.2f}%" if wow is not None else "not available"
    summary = (
        "Decision-ready report: no critical leak triggered. "
        "Maintain current strategy and monitor customer, product, and store lenses weekly."
    )
    diagnosis = DiagnosisBlock(
        what_changed=(
            "A. Detection\n"
            "Customer: No critical anomaly detected in this lens for the current window.\n"
            f"Product: {_compose_lens_detection([], 'product', features)}\n"
            f"Store: Revenue trend is stable under current thresholds (week-over-week change: {wow_text})."
        ),
        likely_why="Why this matters: customer and purchase pattern variance remains within expected range.",
        what_to_do=(
            "B. Decision\n"
            "Customer: Decision: Keep current retention flow active and monitor weekly drift.\n"
            f"Product: {_compose_lens_decision([], 'product', features)}\n"
            "Store: Decision: Keep current growth plan unchanged and review demand signals weekly."
        ),
        what_to_watch_next=(
            "Over the next 7 days, keep baseline watch on Customer: repeat rate and time-to-second-purchase; "
            "Product: refund rate by top SKUs; Store: week-over-week revenue and order count."
        ),
    )
    logger.info("Report built with no critical leak detected")
    return summary, diagnosis
