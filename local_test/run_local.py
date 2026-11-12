"""
Full local run of Project 2: simulates S3 PUT -> Lambda -> DynamoDB using
moto's mocked AWS services, so it runs with zero real AWS cost/credentials.

Usage:
    python local_test/run_local.py
"""
import json
import sys
from pathlib import Path

import boto3
from moto import mock_aws

LAMBDA_DIR = Path(__file__).parent.parent / "lambda"
sys.path.insert(0, str(LAMBDA_DIR))

BUCKET = "de-intern-events-local"
TABLE_NAME = "order-events"
SAMPLES_DIR = Path(__file__).parent / "sample_events"


def make_s3_event(bucket: str, key: str) -> dict:
    return {
        "Records": [
            {"s3": {"bucket": {"name": bucket}, "object": {"key": key}}}
        ]
    }


@mock_aws
def main():
    import os

    os.environ["TABLE_NAME"] = TABLE_NAME
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

    s3 = boto3.client("s3", region_name="us-east-1")
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

    s3.create_bucket(Bucket=BUCKET)
    dynamodb.create_table(
        TableName=TABLE_NAME,
        KeySchema=[{"AttributeName": "event_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "event_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )

    # import handler AFTER mock_aws is active and TABLE_NAME is set, so the
    # module-level boto3 clients inside handler.py bind to the mocked services
    import importlib

    if "handler" in sys.modules:
        importlib.reload(sys.modules["handler"])
    import handler  # noqa: E402

    sample_files = sorted(SAMPLES_DIR.glob("*.json"))
    print(f"Uploading {len(sample_files)} sample events to s3://{BUCKET}/incoming/ ...")
    for f in sample_files:
        key = f"incoming/{f.name}"
        s3.put_object(Bucket=BUCKET, Key=key, Body=f.read_bytes())

    totals = {"processed": 0, "quarantined": 0}
    for f in sample_files:
        key = f"incoming/{f.name}"
        s3_event = make_s3_event(BUCKET, key)
        result = handler.handler(s3_event, None)
        print(f"  {f.name}: {result}")
        totals["processed"] += result["processed"]
        totals["quarantined"] += result["quarantined"]

    print(f"\nTotals: {totals}")

    table = dynamodb.Table(TABLE_NAME)
    items = table.scan()["Items"]
    print(f"\nDynamoDB now has {len(items)} item(s):")
    for item in items:
        print(" ", json.dumps(item, default=str))

    quarantined = s3.list_objects_v2(Bucket=BUCKET, Prefix="quarantine/").get(
        "Contents", []
    )
    print(f"\nQuarantine prefix has {len(quarantined)} object(s):")
    for obj in quarantined:
        head = s3.head_object(Bucket=BUCKET, Key=obj["Key"])
        print(f"  {obj['Key']} -- error: {head.get('Metadata', {}).get('error')}")


if __name__ == "__main__":
    main()
