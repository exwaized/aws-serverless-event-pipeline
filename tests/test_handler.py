import json
import os
import sys
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

sys.path.insert(0, str(Path(__file__).parent.parent / "lambda"))

BUCKET = "test-bucket"
TABLE_NAME = "order-events-test"


@pytest.fixture
def aws_env():
    with mock_aws():
        os.environ["TABLE_NAME"] = TABLE_NAME
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

        s3 = boto3.client("s3", region_name="us-east-1")
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        s3.create_bucket(Bucket=BUCKET)
        dynamodb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[{"AttributeName": "event_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "event_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        import importlib

        if "handler" in sys.modules:
            importlib.reload(sys.modules["handler"])
        import handler

        yield s3, dynamodb, handler


def s3_event(key):
    return {"Records": [{"s3": {"bucket": {"name": BUCKET}, "object": {"key": key}}}]}


def test_valid_event_lands_in_dynamodb(aws_env):
    s3, dynamodb, handler = aws_env
    body = json.dumps(
        {
            "event_id": "evt-ok",
            "event_type": "order_placed",
            "customer_id": "C1",
            "amount": 42.0,
            "occurred_at": "2026-01-01T00:00:00Z",
        }
    )
    s3.put_object(Bucket=BUCKET, Key="incoming/good.json", Body=body)

    result = handler.handler(s3_event("incoming/good.json"), None)

    assert result == {"processed": 1, "quarantined": 0}
    item = dynamodb.Table(TABLE_NAME).get_item(Key={"event_id": "evt-ok"})["Item"]
    assert item["customer_id"] == "C1"


def test_invalid_event_is_quarantined(aws_env):
    s3, dynamodb, handler = aws_env
    body = json.dumps({"event_id": "evt-bad", "event_type": "order_placed"})
    s3.put_object(Bucket=BUCKET, Key="incoming/bad.json", Body=body)

    result = handler.handler(s3_event("incoming/bad.json"), None)

    assert result == {"processed": 0, "quarantined": 1}
    quarantined = s3.list_objects_v2(Bucket=BUCKET, Prefix="quarantine/")["Contents"]
    assert quarantined[0]["Key"] == "quarantine/incoming/bad.json"


def test_quarantine_objects_are_not_reprocessed(aws_env):
    s3, dynamodb, handler = aws_env
    s3.put_object(Bucket=BUCKET, Key="quarantine/incoming/already-bad.json", Body=b"{}")

    result = handler.handler(s3_event("quarantine/incoming/already-bad.json"), None)

    assert result == {"processed": 0, "quarantined": 0}
