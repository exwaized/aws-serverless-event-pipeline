"""
AWS Lambda handler, triggered by an S3 ObjectCreated event.

Reads the newly-uploaded JSON event file from S3, validates + normalizes it
(validation.py), writes the result to DynamoDB, and on any validation
failure moves the offending object to a `quarantine/` prefix in the same
bucket (a cheap dead-letter pattern — no extra queue needed for this scale).

Environment variables (set by infra/template.yaml):
    TABLE_NAME       DynamoDB table to write valid events to
"""
import json
import os
from urllib.parse import unquote_plus

import boto3

from validation import ValidationError, transform, validate

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")

TABLE_NAME = os.environ.get("TABLE_NAME", "order-events")


def handler(event, context):
    table = dynamodb.Table(TABLE_NAME)
    results = {"processed": 0, "quarantined": 0}

    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])

        if key.startswith("quarantine/"):
            continue  # don't reprocess our own dead-letter writes

        obj = s3.get_object(Bucket=bucket, Key=key)
        body = obj["Body"].read()

        try:
            raw_event = json.loads(body)
            validate(raw_event)
            item = transform(raw_event)
            table.put_item(Item=item)
            results["processed"] += 1
        except (ValidationError, json.JSONDecodeError) as exc:
            quarantine_key = f"quarantine/{key}"
            s3.put_object(
                Bucket=bucket,
                Key=quarantine_key,
                Body=body,
                Metadata={"error": str(exc)[:1024]},
            )
            results["quarantined"] += 1

    return results
