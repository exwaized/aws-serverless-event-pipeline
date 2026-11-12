# Serverless Event-Driven Ingestion — S3 → Lambda → DynamoDB

Order events are dropped as JSON files into S3; a Lambda function fires on
each upload, validates/normalizes the event, and writes it to DynamoDB.
Invalid events are quarantined (moved to a `quarantine/` prefix) instead of
silently dropped or crashing the pipeline.

```
S3 (incoming/*.json) --ObjectCreated--> Lambda (validate + transform)
                                              |            |
                                         valid |            | invalid
                                              v            v
                                      DynamoDB table   S3 (quarantine/)
```

## Why this design
- **Event-driven, not polled**: S3 notifications invoke Lambda directly —
  no scheduler, no idle compute cost between events.
- **DynamoDB** over a relational store: event_id as partition key gives
  idempotent writes (same key = overwrite, no dupes), and a GSI on
  `customer_id` supports "all events for this customer" lookups without a
  table scan.
- **Quarantine instead of DLQ-only**: bad payloads are inspectable in S3
  (with the failure reason in object metadata) rather than just logged and
  lost — useful for a data engineer debugging upstream producers.
- **Validation logic isolated** (`lambda/validation.py`) from AWS glue code
  (`lambda/handler.py`) so it's unit-testable with plain pytest, no mocking.

## Run tests (unit — no AWS)
```bash
pip install -r requirements.txt   # or: pip install boto3 moto[s3,dynamodb] pytest
pytest tests/ -v
```

## Run the full pipeline locally (mocked AWS via moto — no AWS account/cost)
```bash
python local_test/run_local.py
```
This spins up a fake S3 bucket + DynamoDB table in-process, uploads the
sample events in `local_test/sample_events/` (one valid, two intentionally
invalid), invokes the real Lambda handler code against them, and prints:
- the per-file `{processed, quarantined}` result
- the DynamoDB rows that got written
- the quarantined S3 objects with their validation-error reason

## Deploy to AWS (SAM)
```bash
sam build --template-file infra/template.yaml
sam deploy --guided
# then:
aws s3 cp local_test/sample_events/good_order.json s3://<bucket>/incoming/good_order.json
aws dynamodb scan --table-name order-events
```

## Files
| Path | Purpose |
|---|---|
| `lambda/validation.py` | Required-field/type/business-rule validation + normalization (pure Python, no AWS SDK) |
| `lambda/handler.py` | Lambda entry point: reads S3 object, validates, writes to DynamoDB or quarantines |
| `infra/template.yaml` | AWS SAM template: S3 bucket + notification, DynamoDB table + GSI, Lambda + IAM policies |
| `tests/test_validation.py` | Pure unit tests for validation rules |
| `tests/test_handler.py` | Integration-style tests against mocked S3/DynamoDB (moto) |
| `local_test/run_local.py` | End-to-end local simulation of the whole pipeline |
| `local_test/sample_events/` | Sample valid/invalid event payloads |
