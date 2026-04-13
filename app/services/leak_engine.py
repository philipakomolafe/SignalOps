# Logging for leak rule evaluation.
import logging
from typing import Dict, List, Optional

from app.models.schemas import FeatureSnapshot, LeakFinding


logger = logging.getLogger(__name__)


def _severity_from_drop(drop_pct: float) -> str:
    if drop_pct <= -25:
        return "critical"
    if drop_pct <= -15:
        return "high"
    return "medium"


def detect_leaks(
    features: FeatureSnapshot,
    comparison_windows: Dict[str, Optional[float]],
) -> List[LeakFinding]:
    logger.info("Evaluating leak rules")
    findings: List[LeakFinding] = []

    wow = features.week_over_week_revenue_change_pct
    if wow is not None and wow <= -12:
        findings.append(
            LeakFinding(
                id="revenue_velocity_drop",
                title="Revenue velocity dropped week-over-week",
                severity=_severity_from_drop(wow),
                what_changed=f"Net revenue changed by {wow:.2f}% versus the previous 7-day period.",
                likely_why=(
                    "Revenue momentum softened in the latest window, usually from weaker acquisition efficiency "
                    "or lower return-customer conversion."
                ),
                what_to_do=(
                    "Review top channels and best-selling SKUs in the last 14 days, then run a targeted "
                    "repeat-buyer recovery campaign."
                ),
                evidence=[
                    f"week_over_week_revenue_change_pct={wow:.2f}",
                    f"repeat_rate={features.repeat_rate:.2f}",
                ],
                context={
                    "wow_revenue_change_pct": round(wow, 2),
                    "repeat_rate": round(features.repeat_rate, 2),
                },
            )
        )

    recent_repeat = comparison_windows.get("recent_repeat_rate")
    previous_repeat = comparison_windows.get("previous_repeat_rate")
    if (
        recent_repeat is not None
        and previous_repeat is not None
        and previous_repeat > 0
        and recent_repeat < previous_repeat * 0.82
    ):
        repeat_delta_pct = ((recent_repeat - previous_repeat) / previous_repeat) * 100.0
        findings.append(
            LeakFinding(
                id="repeat_rate_decline",
                title="Repeat customer behavior is weakening",
                severity="high",
                what_changed=(
                    f"14-day repeat rate moved from {previous_repeat:.2f}% to {recent_repeat:.2f}% "
                    "in the most recent period."
                ),
                likely_why=(
                    "Returning customers are likely delaying repurchase or not receiving strong enough "
                    "post-purchase reactivation cues."
                ),
                what_to_do=(
                    "Launch a 7-14 day post-purchase reactivation flow and tighten repeat-buyer incentives "
                    "for first-time customers."
                ),
                evidence=[
                    f"recent_repeat_rate={recent_repeat:.2f}",
                    f"previous_repeat_rate={previous_repeat:.2f}",
                ],
                context={
                    "recent_repeat_rate": round(recent_repeat, 2),
                    "previous_repeat_rate": round(previous_repeat, 2),
                    "repeat_rate_delta_pct": round(repeat_delta_pct, 2),
                },
            )
        )

    recent_interval = comparison_windows.get("recent_purchase_interval")
    previous_interval = comparison_windows.get("previous_purchase_interval")
    if (
        recent_interval is not None
        and previous_interval is not None
        and previous_interval > 0
        and recent_interval > previous_interval * 1.8
    ):
        interval_delta_pct = ((recent_interval - previous_interval) / previous_interval) * 100.0
        findings.append(
            LeakFinding(
                id="purchase_interval_expansion",
                title="Time between purchases expanded",
                severity="medium",
                what_changed=(
                    f"Average customer purchase interval increased from {previous_interval:.2f} to {recent_interval:.2f} days."
                ),
                likely_why=(
                    "Buy cycles are stretching beyond recent norms, which often appears before silent churn "
                    "and lower revenue density."
                ),
                what_to_do=(
                    "Improve reorder reminders and second-purchase offers, then retest timing against the "
                    "new interval trend."
                ),
                evidence=[
                    f"recent_purchase_interval={recent_interval:.2f}",
                    f"previous_purchase_interval={previous_interval:.2f}",
                ],
                context={
                    "recent_purchase_interval": round(recent_interval, 2),
                    "previous_purchase_interval": round(previous_interval, 2),
                    "purchase_interval_delta_pct": round(interval_delta_pct, 2),
                },
            )
        )

    if features.refund_rate >= 8:
        findings.append(
            LeakFinding(
                id="refund_rate_spike",
                title="Refund pressure is elevated",
                severity="medium",
                what_changed=f"Refund rate is {features.refund_rate:.2f}% of gross revenue.",
                likely_why=(
                    "Refund pressure is above the expected operating band, which usually points to product, "
                    "fulfillment, or expectation mismatch issues."
                ),
                what_to_do=(
                    "Break refunds down by SKU and reason, resolve the top two causes, and monitor the next "
                    "7-day trend for normalization."
                ),
                evidence=[f"refund_rate={features.refund_rate:.2f}"],
                context={
                    "refund_rate": round(features.refund_rate, 2),
                    "refund_threshold": 8.0,
                },
            )
        )

    logger.info("Leak rule evaluation produced %s finding(s)", len(findings))
    return findings
