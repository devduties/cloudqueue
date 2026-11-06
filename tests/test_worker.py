import json
import runpy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import boto3
import pytest
from moto import mock_aws


@pytest.fixture
def worker(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-north-1")
    with mock_aws():
        table = boto3.resource("dynamodb").create_table(
            TableName="jobs",
            KeySchema=[{"AttributeName": "job_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "job_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        monkeypatch.setenv("JOBS_TABLE_NAME", table.name)
        path = Path(__file__).resolve().parents[1] / "lambda" / "worker_handler.py"
        handler = runpy.run_path(str(path))["handler"]
        monkeypatch.setitem(handler.__globals__, "sleep", lambda seconds: None)
        yield handler, table


def make_job(table, status="PENDING", age=0, **attributes):
    job_id = str(uuid4())
    table.put_item(Item={
        "job_id": job_id,
        "status": status,
        "payload": "example",
        "updated_at": (datetime.now(UTC) - timedelta(seconds=age)).isoformat(),
        **attributes,
    })
    return {"job_id": job_id}


def message(key, message_id="message-1"):
    return {"messageId": message_id, "body": json.dumps(key)}


def test_worker_claims_job_and_skips_duplicate_delivery(worker, monkeypatch):
    handler, table = worker
    key = make_job(table)
    calls = []

    def work(seconds):
        assert table.get_item(Key=key)["Item"]["status"] == "PROCESSING"
        calls.append(seconds)

    monkeypatch.setitem(handler.__globals__, "sleep", work)
    event = {"Records": [message(key)]}

    assert handler(event, None) == {"batchItemFailures": []}
    assert handler(event, None) == {"batchItemFailures": []}
    assert calls == [1]
    assert table.get_item(Key=key)["Item"]["status"] == "DONE"


def test_work_failure_is_recorded_and_message_can_retry(worker, monkeypatch):
    handler, table = worker
    key = make_job(table)
    event = {"Records": [message(key)]}

    def fail(seconds):
        raise RuntimeError("simulated work failure")

    with monkeypatch.context() as patch:
        patch.setitem(handler.__globals__, "sleep", fail)
        assert handler(event, None) == {"batchItemFailures": [{"itemIdentifier": "message-1"}]}

    job = table.get_item(Key=key)["Item"]
    assert job["status"] == "FAILED"
    assert job["error"] == "Job processing failed"
    assert handler(event, None) == {"batchItemFailures": []}
    job = table.get_item(Key=key)["Item"]
    assert job["status"] == "DONE"
    assert "error" not in job


def test_worker_only_reclaims_expired_claims(worker):
    handler, table = worker
    active = make_job(table, status="PROCESSING")
    expired = make_job(table, status="PROCESSING", age=61)
    rejected = make_job(table, status="FAILED", error="Queue rejected the job")
    event = {
        "Records": [
            message(active, "active"),
            message(expired, "expired"),
            message(rejected, "rejected"),
        ]
    }

    assert handler(event, None) == {"batchItemFailures": [{"itemIdentifier": "active"}]}
    assert table.get_item(Key=active)["Item"]["status"] == "PROCESSING"
    assert table.get_item(Key=expired)["Item"]["status"] == "DONE"
    assert table.get_item(Key=rejected)["Item"]["status"] == "FAILED"


def test_bad_messages_do_not_block_valid_jobs(worker):
    handler, table = worker
    key = make_job(table)
    missing = {"job_id": str(uuid4())}
    event = {"Records": [
        {"messageId": "malformed", "body": "not json"},
        message(missing, "missing"),
        message(key),
    ]}

    assert handler(event, None) == {
        "batchItemFailures": [{"itemIdentifier": "malformed"}, {"itemIdentifier": "missing"}]
    }
    assert table.get_item(Key=key)["Item"]["status"] == "DONE"
    assert "Item" not in table.get_item(Key=missing)
