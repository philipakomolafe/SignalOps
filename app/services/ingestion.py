# CSV parsing + normalization helpers.
import csv
import io
# Logging for ingestion failures and normalization diagnostics.
import logging
# Dataclass used as normalized event record.
from dataclasses import dataclass, field
# Datetime parser for order timestamp normalization.
from datetime import datetime
# Type hints for better readability and tooling.
from typing import Dict, List, Optional


# Required logical fields needed by the MVP analysis pipeline.
REQUIRED_FIELDS = ("order_id", "customer_id", "order_date", "order_total")
# Alias map to support common naming differences across ecommerce CSV exports.
COLUMN_ALIASES = {
    "order_id": ["order_id", "id", "name", "order_name"],
    "customer_id": ["customer_id", "customer", "customer_email", "email"],
    "order_date": ["order_date", "created_at", "processed_at", "date", "order_created_at"],
    "order_total": ["order_total", "total_price", "total", "amount", "gross_sales"],
    "refunded_amount": ["refunded_amount", "refund_total", "total_refunded", "refunds"],
    "currency": ["currency", "presentment_currency", "shop_currency"],
    "product_id": ["product_id", "product", "item_id"],
    "variant_id": ["variant_id", "variant", "item_variant_id"],
    "sku": ["sku", "item_sku", "variant_sku"],
    "product_title": ["product_title", "product_name", "title", "item_name"],
    "quantity": ["quantity", "qty", "item_quantity"],
}


logger = logging.getLogger(__name__)


@dataclass
class NormalizedLineItem:
    """Canonical product row shape attached to an order event."""
    product_id: Optional[str]
    variant_id: Optional[str]
    sku: str
    title: str
    quantity: int
    gross_revenue: float
    refunded_amount: float


@dataclass
class NormalizedOrderEvent:
    """Canonical order event shape consumed by downstream analytics modules."""
    # Unique order identifier from source system.
    order_id: str
    # Customer identifier (email or id), used for cohort/retention logic.
    customer_id: str
    # Normalized order timestamp.
    ordered_at: datetime
    # Gross order amount.
    order_total: float
    # Refunded amount for the same order.
    refunded_amount: float
    # Currency code (e.g., USD).
    currency: str
    # Optional product rows attached to this order.
    line_items: List[NormalizedLineItem] = field(default_factory=list)


class CSVNormalizationError(ValueError):
    """Raised when uploaded CSV cannot be normalized into required schema."""

    pass


def _pick_column(fieldnames: List[str], logical_name: str) -> Optional[str]:
    """Resolve a logical field name to a real CSV column using aliases."""
    # Build case-insensitive map: lowercase_name -> original_name.
    lowered_map: Dict[str, str] = {name.strip().lower(): name for name in fieldnames}
    # Return first matching alias found in CSV header.
    for alias in COLUMN_ALIASES[logical_name]:
        if alias in lowered_map:
            return lowered_map[alias]
    # No matching alias found.
    return None


def _parse_float(raw: str, field_name: str) -> float:
    """Parse numeric string to float; blank values are treated as 0."""
    # Trim whitespace and remove comma separators.
    value = (raw or "").strip().replace(",", "")
    # Empty numeric cells become zero for tolerant ingestion.
    if not value:
        return 0.0
    try:
        # Parse as floating-point number.
        return float(value)
    except ValueError as exc:
        logger.warning("Invalid numeric value for %s: %r", field_name, raw)
        # Raise normalization-specific error with field context.
        raise CSVNormalizationError(f"Invalid numeric value in {field_name}: '{raw}'") from exc


def _parse_int(raw: str, field_name: str, default: int = 0) -> int:
    """Parse integer-like strings; blank values fall back to the provided default."""
    value = (raw or "").strip().replace(",", "")
    if not value:
        return default
    try:
        return int(float(value))
    except ValueError as exc:
        logger.warning("Invalid integer value for %s: %r", field_name, raw)
        raise CSVNormalizationError(f"Invalid integer value in {field_name}: '{raw}'") from exc


def _parse_datetime(raw: str) -> datetime:
    """Parse order timestamp from common datetime/date formats."""
    # Normalize input string.
    value = (raw or "").strip()
    # Date is mandatory for time-based analysis.
    if not value:
        logger.warning("Missing order date during normalization")
        raise CSVNormalizationError("Missing order date")

    # Support ISO-like UTC timestamps with trailing Z.
    iso_value = value.replace("Z", "+00:00")
    try:
        # First attempt: native ISO parser.
        return datetime.fromisoformat(iso_value)
    except ValueError:
        # Fall through to known legacy formats.
        pass

    # Additional date formats commonly seen in exports.
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
    ]
    # Try each format until one succeeds.
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    # If no parser worked, surface explicit normalization error.
    logger.warning("Could not parse order_date value: %r", raw)
    raise CSVNormalizationError(f"Could not parse order_date value: '{raw}'")


def normalize_orders_csv(csv_text: str, default_currency: str = "USD") -> List[NormalizedOrderEvent]:
    """Normalize raw CSV text into sorted normalized order events."""
    logger.info("Starting CSV normalization")
    # Parse CSV rows into dicts keyed by header columns.
    reader = csv.DictReader(io.StringIO(csv_text))
    # Header row is required for alias-based field resolution.
    if not reader.fieldnames:
        logger.warning("CSV normalization failed: no header row")
        raise CSVNormalizationError("CSV has no header row")

    # Drop empty header values and preserve original names.
    fieldnames = [name for name in reader.fieldnames if name]
    # Resolve each logical field to the concrete CSV column name.
    selected = {name: _pick_column(fieldnames, name) for name in COLUMN_ALIASES}

    # Validate all required fields are mapped.
    missing_required = [field for field in REQUIRED_FIELDS if not selected.get(field)]
    if missing_required:
        missing = ", ".join(missing_required)
        logger.warning("CSV missing required columns: %s", missing)
        raise CSVNormalizationError(
            f"CSV missing required columns: {missing}. Accepted aliases include: {COLUMN_ALIASES}"
        )

    # Accumulator for valid normalized events.
    events: List[NormalizedOrderEvent] = []
    # Enumerate data rows; start=2 because row 1 is header.
    for row_index, row in enumerate(reader, start=2):
        # Extract order/customer identifiers.
        order_id = str(row.get(selected["order_id"], "")).strip()
        customer_id = str(row.get(selected["customer_id"], "")).strip()
        # Skip rows missing key identifiers.
        if not order_id or not customer_id:
            continue

        try:
            # Parse date and amount fields with validation.
            ordered_at = _parse_datetime(str(row.get(selected["order_date"], "")))
            order_total = _parse_float(str(row.get(selected["order_total"], "")), "order_total")
            refunded_amount = _parse_float(str(row.get(selected["refunded_amount"], "")), "refunded_amount")
        except CSVNormalizationError as exc:
            # Attach row number for user-friendly debugging.
            logger.warning("CSV normalization failed at row %s: %s", row_index, exc)
            raise CSVNormalizationError(f"Row {row_index}: {exc}") from exc

        # Resolve currency from mapped column or fallback default.
        currency_value = selected.get("currency")
        currency = (
            str(row.get(currency_value, default_currency)).strip().upper() if currency_value else default_currency
        )

        line_items: List[NormalizedLineItem] = []
        product_title_column = selected.get("product_title")
        product_title = str(row.get(product_title_column, "")).strip() if product_title_column else ""
        product_id_column = selected.get("product_id")
        variant_id_column = selected.get("variant_id")
        sku_column = selected.get("sku")
        quantity_column = selected.get("quantity")
        product_id = str(row.get(product_id_column, "")).strip() if product_id_column else ""
        variant_id = str(row.get(variant_id_column, "")).strip() if variant_id_column else ""
        sku = str(row.get(sku_column, "")).strip() if sku_column else ""
        if product_title or product_id or variant_id or sku:
            quantity = _parse_int(str(row.get(quantity_column, "")), "quantity", default=1) if quantity_column else 1
            line_items.append(
                NormalizedLineItem(
                    product_id=product_id or None,
                    variant_id=variant_id or None,
                    sku=sku,
                    title=product_title or sku or product_id or variant_id or order_id,
                    quantity=max(quantity, 0),
                    gross_revenue=order_total,
                    refunded_amount=refunded_amount,
                )
            )

        # Build normalized event object and append.
        events.append(
            NormalizedOrderEvent(
                order_id=order_id,
                customer_id=customer_id,
                ordered_at=ordered_at,
                order_total=order_total,
                refunded_amount=refunded_amount,
                currency=currency or default_currency,
                line_items=line_items,
            )
        )

    # Ensure at least one valid event exists.
    if not events:
        logger.warning("CSV normalization produced no valid rows")
        raise CSVNormalizationError("No valid rows found in CSV")

    # Sort chronologically for deterministic downstream computations.
    events.sort(key=lambda e: e.ordered_at)
    logger.info("CSV normalization completed successfully with %s events", len(events))
    return events


def normalize_shopify_orders(
    orders: List[Dict[str, object]],
    default_currency: str = "USD",
) -> List[NormalizedOrderEvent]:
    """Normalize Shopify Admin API order objects into canonical events."""
    events: List[NormalizedOrderEvent] = []

    for order in orders:
        order_id = str(order.get("id") or order.get("name") or "").strip()
        if not order_id:
            continue

        customer_id = ""
        customer_obj = order.get("customer")
        if isinstance(customer_obj, dict):
            raw_customer_id = customer_obj.get("id")
            raw_customer_email = customer_obj.get("email")
            if raw_customer_id is not None:
                customer_id = str(raw_customer_id).strip()
            elif raw_customer_email:
                customer_id = str(raw_customer_email).strip().lower()

        if not customer_id:
            fallback_email = str(order.get("email") or "").strip().lower()
            customer_id = fallback_email or f"guest:{order_id}"

        ordered_at = _parse_datetime(str(order.get("created_at") or order.get("processed_at") or ""))

        order_total = _parse_float(str(order.get("current_total_price") or order.get("total_price") or "0"), "order_total")

        refunded_amount = 0.0
        refunds_obj = order.get("refunds")
        if isinstance(refunds_obj, list):
            for refund in refunds_obj:
                if not isinstance(refund, dict):
                    continue
                transactions = refund.get("transactions")
                if isinstance(transactions, list):
                    for transaction in transactions:
                        if not isinstance(transaction, dict):
                            continue
                        refunded_amount += _parse_float(str(transaction.get("amount") or "0"), "refunded_amount")

        currency = str(order.get("currency") or order.get("presentment_currency") or default_currency).strip().upper()
        if not currency:
            currency = default_currency

        refund_amount_by_line_item_id: Dict[str, float] = {}
        if isinstance(refunds_obj, list):
            for refund in refunds_obj:
                if not isinstance(refund, dict):
                    continue
                refund_line_items = refund.get("refund_line_items")
                if not isinstance(refund_line_items, list):
                    continue
                for refund_line_item in refund_line_items:
                    if not isinstance(refund_line_item, dict):
                        continue
                    line_item = refund_line_item.get("line_item")
                    if not isinstance(line_item, dict):
                        continue
                    line_item_id = str(line_item.get("id") or "").strip()
                    if not line_item_id:
                        continue
                    subtotal = refund_line_item.get("subtotal")
                    if subtotal is None:
                        unit_price = _parse_float(str(line_item.get("price") or "0"), "line_item_price")
                        quantity = _parse_int(str(refund_line_item.get("quantity") or "0"), "refund_quantity")
                        amount = unit_price * max(quantity, 0)
                    else:
                        amount = _parse_float(str(subtotal), "refund_line_subtotal")
                    refund_amount_by_line_item_id[line_item_id] = (
                        refund_amount_by_line_item_id.get(line_item_id, 0.0) + max(amount, 0.0)
                    )

        line_items: List[NormalizedLineItem] = []
        raw_line_items = order.get("line_items")
        if isinstance(raw_line_items, list):
            for raw_line_item in raw_line_items:
                if not isinstance(raw_line_item, dict):
                    continue
                quantity = _parse_int(str(raw_line_item.get("quantity") or "0"), "quantity")
                unit_price = _parse_float(str(raw_line_item.get("price") or "0"), "line_item_price")
                total_discount = _parse_float(str(raw_line_item.get("total_discount") or "0"), "line_item_discount")
                gross_revenue = max((unit_price * max(quantity, 0)) - total_discount, 0.0)
                line_item_id = str(raw_line_item.get("id") or "").strip()
                refunded_line_amount = refund_amount_by_line_item_id.get(line_item_id, 0.0)
                line_items.append(
                    NormalizedLineItem(
                        product_id=str(raw_line_item.get("product_id") or "").strip() or None,
                        variant_id=str(raw_line_item.get("variant_id") or "").strip() or None,
                        sku=str(raw_line_item.get("sku") or "").strip(),
                        title=str(raw_line_item.get("title") or raw_line_item.get("name") or order_id).strip(),
                        quantity=max(quantity, 0),
                        gross_revenue=gross_revenue,
                        refunded_amount=max(refunded_line_amount, 0.0),
                    )
                )

        events.append(
            NormalizedOrderEvent(
                order_id=order_id,
                customer_id=customer_id,
                ordered_at=ordered_at,
                order_total=order_total,
                refunded_amount=refunded_amount,
                currency=currency,
                line_items=line_items,
            )
        )

    if not events:
        raise CSVNormalizationError("No valid Shopify orders found")

    events.sort(key=lambda e: e.ordered_at)
    return events
