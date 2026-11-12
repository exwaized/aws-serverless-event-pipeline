"""
Validation/transform logic for incoming order-event JSON objects, kept
separate from handler.py so it's trivially unit-testable without any AWS
mocking.
"""
from datetime import datetime, timezone
from decimal import Decimal

REQUIRED_FIELDS = {"event_id", "event_type", "customer_id", "amount", "occurred_at"}
VALID_EVENT_TYPES = {"order_placed", "order_cancelled", "order_refunded"}


class ValidationError(Exception):
    pass


def validate(event: dict) -> None:
    missing = REQUIRED_FIELDS - event.keys()
    if missing:
        raise ValidationError(f"missing required fields: {sorted(missing)}")

    if event["event_type"] not in VALID_EVENT_TYPES:
        raise ValidationError(f"invalid event_type: {event['event_type']!r}")

    if not isinstance(event["amount"], (int, float)):
        raise ValidationError("amount must be numeric")

    if event["amount"] < 0 and event["event_type"] == "order_placed":
        raise ValidationError("order_placed amount cannot be negative")

    try:
        datetime.fromisoformat(event["occurred_at"].replace("Z", "+00:00"))
    except (ValueError, AttributeError) as exc:
        raise ValidationError(f"occurred_at is not a valid ISO-8601 timestamp: {exc}")


def transform(event: dict) -> dict:
    """Normalizes a validated event into the item shape stored in DynamoDB."""
    occurred_at = datetime.fromisoformat(event["occurred_at"].replace("Z", "+00:00"))
    return {
        "event_id": event["event_id"],
        "customer_id": event["customer_id"],
        "event_type": event["event_type"],
        "amount": Decimal(str(event["amount"])),
        "occurred_at": occurred_at.astimezone(timezone.utc).isoformat(),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }
