from typing import List, Tuple

from app.models.schemas import DiagnosisBlock, FeatureSnapshot, LeakFinding


def build_report(features: FeatureSnapshot, findings: List[LeakFinding]) -> Tuple[str, DiagnosisBlock]:
    if findings:
        top = findings[0]
        summary = (
            f"Detected {len(findings)} potential revenue leak(s). "
            f"Top signal: {top.title.lower()}."
        )
        diagnosis = DiagnosisBlock(
            what_changed=top.what_changed,
            likely_why=top.likely_why,
            what_to_do=top.what_to_do,
        )
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
    return summary, diagnosis
