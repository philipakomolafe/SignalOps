from typing import Dict, List, Optional

from app.models.schemas import FeatureSnapshot, LeakFinding


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
    findings: List[LeakFinding] = []

    wow = features.week_over_week_revenue_change_pct
    if wow is not None and wow <= -12:
        findings.append(
            LeakFinding(
                id="revenue_velocity_drop",
                title="Revenue velocity dropped week-over-week",
                severity=_severity_from_drop(wow),
                what_changed=f"Net revenue changed by {wow:.2f}% versus the previous 7-day period.",
                likely_why="Top-line demand or repeat purchase momentum slowed materially in the current week.",
                what_to_do="Audit high-value products and channels from the last 14 days, then launch a repeat-buyer recovery flow.",
                evidence=[
                    f"week_over_week_revenue_change_pct={wow:.2f}",
                    f"repeat_rate={features.repeat_rate:.2f}",
                ],
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
        findings.append(
            LeakFinding(
                id="repeat_rate_decline",
                title="Repeat customer behavior is weakening",
                severity="high",
                what_changed=(
                    f"14-day repeat rate moved from {previous_repeat:.2f}% to {recent_repeat:.2f}% "
                    "in the most recent period."
                ),
                likely_why="Returning customers are taking longer to repurchase or dropping out after their first order.",
                what_to_do="Deploy a 7-14 day post-purchase reactivation campaign and review returning-customer discount strategy.",
                evidence=[
                    f"recent_repeat_rate={recent_repeat:.2f}",
                    f"previous_repeat_rate={previous_repeat:.2f}",
                ],
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
        findings.append(
            LeakFinding(
                id="purchase_interval_expansion",
                title="Time between purchases expanded",
                severity="medium",
                what_changed=(
                    f"Average customer purchase interval increased from {previous_interval:.2f} to {recent_interval:.2f} days."
                ),
                likely_why="Customer buy cycles are stretching, which often precedes silent churn and revenue leakage.",
                what_to_do="Improve reorder nudges, replenish reminders, and timing of retention offers for second purchase conversion.",
                evidence=[
                    f"recent_purchase_interval={recent_interval:.2f}",
                    f"previous_purchase_interval={previous_interval:.2f}",
                ],
            )
        )

    if features.refund_rate >= 8:
        findings.append(
            LeakFinding(
                id="refund_rate_spike",
                title="Refund pressure is elevated",
                severity="medium",
                what_changed=f"Refund rate is {features.refund_rate:.2f}% of gross revenue.",
                likely_why="A product quality, fulfillment, or expectation mismatch issue may be driving avoidable leakage.",
                what_to_do="Break down refunds by SKU and reason code; fix top two causes and monitor 7-day trend.",
                evidence=[f"refund_rate={features.refund_rate:.2f}"],
            )
        )

    return findings
