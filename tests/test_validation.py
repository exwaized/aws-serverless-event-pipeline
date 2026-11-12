import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "lambda"))

from validation import ValidationError, transform, validate  # noqa: E402

GOOD_EVENT = {
    "event_id": "evt-1",
    "event_type": "order_placed",
    "customer_id": "C1",
    "amount": 10.5,
    "occurred_at": "2026-01-01T00:00:00Z",
}


def test_valid_event_passes():
    validate(GOOD_EVENT)  # should not raise


def test_transform_normalizes_fields():
    item = transform(GOOD_EVENT)
    assert item["event_id"] == "evt-1"
    assert item["amount"] == 10.5
    assert "ingested_at" in item


def test_missing_required_field_raises():
    bad = {k: v for k, v in GOOD_EVENT.items() if k != "customer_id"}
    with pytest.raises(ValidationError, match="missing required fields"):
        validate(bad)


def test_invalid_event_type_raises():
    bad = {**GOOD_EVENT, "event_type": "not_a_real_type"}
    with pytest.raises(ValidationError, match="invalid event_type"):
        validate(bad)


def test_negative_amount_on_order_placed_raises():
    bad = {**GOOD_EVENT, "amount": -5}
    with pytest.raises(ValidationError, match="negative"):
        validate(bad)


def test_negative_amount_allowed_for_refund():
    refund = {**GOOD_EVENT, "event_type": "order_refunded", "amount": -5}
    validate(refund)  # refunds may be negative


def test_bad_timestamp_raises():
    bad = {**GOOD_EVENT, "occurred_at": "not-a-date"}
    with pytest.raises(ValidationError, match="ISO-8601"):
        validate(bad)
