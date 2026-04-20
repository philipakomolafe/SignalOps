# Helpers for grouping and aggregation operations.
from collections import defaultdict
# Logging for analysis diagnostics.
import logging
# Date arithmetic for comparison windows.
from datetime import date, timedelta
# Mean computation for interval-based metrics.
from statistics import mean
# Type hints for readability.
from typing import Dict, List, Optional, Tuple

# Response models used by feature snapshots.
from app.models.schemas import (
    CohortRetentionPoint,
    FeatureSnapshot,
    ProductPerformanceItem,
    ProductPerformanceSnapshot,
)
# Normalized event shape produced by ingestion service.
from app.services.ingestion import NormalizedLineItem, NormalizedOrderEvent


logger = logging.getLogger(__name__)


def _line_item_key(line_item: NormalizedLineItem) -> str:
    """Return a stable grouping key for product analytics."""
    return (
        line_item.product_id
        or line_item.variant_id
        or line_item.sku
        or line_item.title.strip().lower()
    )


def _safe_pct_change(current: float, previous: float) -> Optional[float]:
    """Return percentage change; None when previous value is zero."""
    # Avoid division-by-zero for baseline period.
    if previous == 0:
        return None
    # Standard percent-change formula.
    return ((current - previous) / previous) * 100.0


def _window_revenue(events: List[NormalizedOrderEvent], start: date, end: date) -> float:
    """Compute net revenue within inclusive date window."""
    # Sum net order values, clamped at zero per order.
    return sum(
        max(event.order_total - event.refunded_amount, 0.0)
        for event in events
        if start <= event.ordered_at.date() <= end
    )


def _average_time_to_second_purchase(events_by_customer: Dict[str, List[NormalizedOrderEvent]]) -> Optional[float]:
    """Average days from first to second purchase across customers."""
    # Collect day deltas for customers with at least two orders.
    deltas = []
    for customer_events in events_by_customer.values():
        if len(customer_events) >= 2:
            delta = customer_events[1].ordered_at - customer_events[0].ordered_at
            deltas.append(delta.total_seconds() / 86400.0)
    # Return arithmetic mean when at least one delta exists.
    return mean(deltas) if deltas else None


def _average_purchase_interval(events_by_customer: Dict[str, List[NormalizedOrderEvent]]) -> Optional[float]:
    """Average days between consecutive purchases across all customers."""
    # Collect intervals across each customer's order timeline.
    deltas = []
    for customer_events in events_by_customer.values():
        if len(customer_events) < 2:
            continue
        for index in range(1, len(customer_events)):
            delta = customer_events[index].ordered_at - customer_events[index - 1].ordered_at
            deltas.append(delta.total_seconds() / 86400.0)
    # Return mean interval if any intervals were observed.
    return mean(deltas) if deltas else None


def _build_cohort_retention(events_by_customer: Dict[str, List[NormalizedOrderEvent]]) -> List[CohortRetentionPoint]:
    """Build 30-day retention stats grouped by customer first-order cohort month."""
    # Cohort accumulator: {YYYY-MM: {count, retained}}.
    cohorts: Dict[str, Dict[str, int]] = defaultdict(lambda: {"count": 0, "retained": 0})

    # Walk customer timelines to assign cohorts and retention outcomes.
    for customer_events in events_by_customer.values():
        # Cohort key is first purchase month.
        first_event = customer_events[0]
        cohort_key = first_event.ordered_at.strftime("%Y-%m")
        cohorts[cohort_key]["count"] += 1

        # Retained means any subsequent order within 30 days of first order.
        retained = any(
            (event.ordered_at - first_event.ordered_at).total_seconds() <= 30 * 86400
            and (event.ordered_at - first_event.ordered_at).total_seconds() > 0
            for event in customer_events[1:]
        )
        if retained:
            cohorts[cohort_key]["retained"] += 1

    # Convert aggregated dict to sorted model list.
    points: List[CohortRetentionPoint] = []
    for cohort_key in sorted(cohorts.keys()):
        stats = cohorts[cohort_key]
        count = stats["count"]
        retained = stats["retained"]
        # Retention rate as percent.
        rate = (retained / count * 100.0) if count else 0.0
        points.append(
            CohortRetentionPoint(
                cohort=cohort_key,
                customer_count=count,
                retained_30d=retained,
                retention_rate_30d=round(rate, 2),
            )
        )
    return points


def _window_repeat_and_interval(
    events: List[NormalizedOrderEvent],
    start: date,
    end: date,
) -> Tuple[Optional[float], Optional[float]]:
    """Compute repeat-rate and purchase-interval metrics for a date window."""
    # Filter events that land inside the requested date range.
    window_events = [event for event in events if start <= event.ordered_at.date() <= end]
    # No events means no metrics.
    if not window_events:
        return None, None

    # Group window events by customer.
    by_customer: Dict[str, List[NormalizedOrderEvent]] = defaultdict(list)
    for event in window_events:
        by_customer[event.customer_id].append(event)

    # Compute repeat-rate from customers with at least two orders.
    customer_count = len(by_customer)
    repeat_count = sum(1 for e in by_customer.values() if len(e) >= 2)
    repeat_rate = (repeat_count / customer_count * 100.0) if customer_count else None
    # Compute average purchase interval for window.
    interval = _average_purchase_interval(by_customer)
    return repeat_rate, interval


def _build_product_performance(events: List[NormalizedOrderEvent]) -> ProductPerformanceSnapshot:
    """Aggregate product-level KPIs from normalized line items."""
    grouped: Dict[str, Dict[str, object]] = {}
    total_units = 0

    for event in events:
        seen_products_in_order = set()
        for line_item in event.line_items:
            key = _line_item_key(line_item)
            if not key:
                continue
            total_units += max(line_item.quantity, 0)
            if key not in grouped:
                grouped[key] = {
                    "product_id": line_item.product_id,
                    "variant_id": line_item.variant_id,
                    "sku": line_item.sku or None,
                    "title": line_item.title,
                    "units_sold": 0,
                    "gross_revenue": 0.0,
                    "refund_amount": 0.0,
                    "order_count": 0,
                }
            stats = grouped[key]
            stats["units_sold"] = int(stats["units_sold"]) + max(line_item.quantity, 0)
            stats["gross_revenue"] = float(stats["gross_revenue"]) + max(line_item.gross_revenue, 0.0)
            stats["refund_amount"] = float(stats["refund_amount"]) + max(line_item.refunded_amount, 0.0)
            if key not in seen_products_in_order:
                stats["order_count"] = int(stats["order_count"]) + 1
                seen_products_in_order.add(key)

    items: List[ProductPerformanceItem] = []
    for stats in grouped.values():
        gross_revenue = float(stats["gross_revenue"])
        refund_amount = float(stats["refund_amount"])
        items.append(
            ProductPerformanceItem(
                product_id=stats["product_id"],
                variant_id=stats["variant_id"],
                sku=stats["sku"],
                title=str(stats["title"]),
                order_count=int(stats["order_count"]),
                units_sold=int(stats["units_sold"]),
                gross_revenue=round(gross_revenue, 2),
                net_revenue=round(max(gross_revenue - refund_amount, 0.0), 2),
                refund_amount=round(refund_amount, 2),
                refund_rate=round((refund_amount / gross_revenue) * 100.0, 2) if gross_revenue else 0.0,
            )
        )

    top_by_revenue = sorted(
        items,
        key=lambda item: (item.net_revenue, item.gross_revenue, item.units_sold),
        reverse=True,
    )[:5]
    top_by_refund_rate = sorted(
        [item for item in items if item.gross_revenue > 0 or item.refund_amount > 0],
        key=lambda item: (item.refund_rate, item.refund_amount, item.gross_revenue),
        reverse=True,
    )[:5]

    return ProductPerformanceSnapshot(
        products_analyzed=len(items),
        units_sold=total_units,
        top_products_by_revenue=top_by_revenue,
        top_products_by_refund_rate=top_by_refund_rate,
    )


def generate_feature_snapshot(events: List[NormalizedOrderEvent]) -> FeatureSnapshot:
    """Generate all primary features consumed by leak detection and reporting."""
    logger.info("Generating feature snapshot for %s events", len(events))
    # Build customer timelines for customer-centric metrics.
    by_customer: Dict[str, List[NormalizedOrderEvent]] = defaultdict(list)
    for event in events:
        by_customer[event.customer_id].append(event)

    # Ensure each customer timeline is chronological.
    for customer_events in by_customer.values():
        customer_events.sort(key=lambda e: e.ordered_at)

    # Core revenue aggregates.
    gross_revenue = sum(event.order_total for event in events)
    total_refunds = sum(event.refunded_amount for event in events)
    total_revenue = sum(max(event.order_total - event.refunded_amount, 0.0) for event in events)

    # Core volume/customer aggregates.
    order_count = len(events)
    customer_count = len(by_customer)
    repeat_customers = sum(1 for customer_events in by_customer.values() if len(customer_events) >= 2)

    # Build current and previous 7-day windows ending at latest event day.
    latest_day = events[-1].ordered_at.date()
    current_start = latest_day - timedelta(days=6)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=6)

    # Compute WoW revenue trend and timing metrics.
    current_week_rev = _window_revenue(events, current_start, latest_day)
    previous_week_rev = _window_revenue(events, previous_start, previous_end)
    wow_change = _safe_pct_change(current_week_rev, previous_week_rev)
    avg_second_purchase = _average_time_to_second_purchase(by_customer)
    avg_purchase_interval = _average_purchase_interval(by_customer)

    # Return typed feature snapshot rounded for UI readability.
    snapshot = FeatureSnapshot(
        total_revenue=round(total_revenue, 2),
        order_count=order_count,
        customer_count=customer_count,
        revenue_per_user=round(total_revenue / customer_count, 2) if customer_count else 0.0,
        purchase_frequency=round(order_count / customer_count, 2) if customer_count else 0.0,
        repeat_rate=round((repeat_customers / customer_count) * 100.0, 2) if customer_count else 0.0,
        refund_rate=round((total_refunds / gross_revenue) * 100.0, 2) if gross_revenue else 0.0,
        avg_time_to_second_purchase_days=(
            round(avg_second_purchase, 2)
            if avg_second_purchase is not None
            else None
        ),
        avg_purchase_interval_days=(
            round(avg_purchase_interval, 2)
            if avg_purchase_interval is not None
            else None
        ),
        week_over_week_revenue_change_pct=round(wow_change, 2) if wow_change is not None else None,
        cohort_retention_30d=_build_cohort_retention(by_customer),
        product_performance=_build_product_performance(events),
    )



    logger.info(
        "Feature snapshot ready: revenue=%.2f orders=%s customers=%s",
        snapshot.total_revenue,
        snapshot.order_count,
        snapshot.customer_count,
    )
    return snapshot
def compute_comparison_windows(events: List[NormalizedOrderEvent]) -> Dict[str, Optional[float]]:
    """Compute recent vs previous window comparison metrics for leak heuristics."""
    logger.info("Computing comparison windows for %s events", len(events))
    # Anchor on latest event date.
    latest_day = events[-1].ordered_at.date()

    # Define two consecutive 14-day windows.
    recent_start = latest_day - timedelta(days=13)
    recent_end = latest_day

    prev_end = recent_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=13)

    # Compute repeat-rate and interval for both windows.
    recent_repeat_rate, recent_interval = _window_repeat_and_interval(events, recent_start, recent_end)
    prev_repeat_rate, prev_interval = _window_repeat_and_interval(events, prev_start, prev_end)

    # Return rounded comparison values used by leak engine.
    result = {
        "recent_repeat_rate": round(recent_repeat_rate, 2) if recent_repeat_rate is not None else None,
        "previous_repeat_rate": round(prev_repeat_rate, 2) if prev_repeat_rate is not None else None,
        "recent_purchase_interval": round(recent_interval, 2) if recent_interval is not None else None,
        "previous_purchase_interval": round(prev_interval, 2) if prev_interval is not None else None,
    }

    logger.info("Comparison windows computed")
    return result
