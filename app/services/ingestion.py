# CSV parsing + normalization helpers.
import csv
import io
# Logging for ingestion failures and normalization diagnostics.
import logging
# Dataclass used as normalized event record.
from dataclasses import dataclass
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
}


logger = logging.getLogger(__name__)


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

        # Build normalized event object and append.
        events.append(
            NormalizedOrderEvent(
                order_id=order_id,
                customer_id=customer_id,
                ordered_at=ordered_at,
                order_total=order_total,
                refunded_amount=refunded_amount,
                currency=currency or default_currency,
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
