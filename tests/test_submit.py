import base64
import json
import runpy
from pathlib import Path
from uuid import UUID

import boto3
import pytest
from botocore.exceptions import ReadTimeoutError
from moto import mock_aws


@pytest.fixture
def submit(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-north-1")
    with mock_aws():
        table = boto3.resource("dynamodb").create_table(
            TableName="jobs",
            KeySchema=[{"AttributeName": "job_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "job_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        sqs = boto3.client("sqs")
        queue_url = sqs.create_queue(QueueName="jobs")["QueueUrl"]
        monkeypatch.setenv("JOBS_TABLE_NAME", table.name)
        monkeypatch.setenv("JOBS_QUEUE_URL", queue_url)
        module_path = Path(__file__).resolve().parents[1] / "lambda" / "submit_handler.py"
        handler = runpy.run_path(str(module_path))["handler"]
        yield handler, table, sqs, queue_url


@pytest.mark.parametrize("payload,encoded", [("example", False), ("", False), ("café", True)])
def test_submit_stores_and_enqueues_job(submit, payload, encoded):
    handler, table, sqs, queue_url = submit
    body = json.dumps({"payload": payload}, ensure_ascii=False)
    if encoded:
        body = base64.b64encode(body.encode()).decode()

    result = handler({"body": body, "isBase64Encoded": encoded}, None)

    assert result["statusCode"] == 202
    assert result["headers"]["Content-Type"] == "application/json"
    data = json.loads(result["body"])
    job_id = data["job_id"]
    assert UUID(job_id).version == 4
    assert data["status"] == "PENDING"
    job = table.get_item(Key={"job_id": job_id})["Item"]
    assert job["payload"] == payload
    assert job["status"] == "PENDING"
    assert job["created_at"] == job["updated_at"]
    messages = sqs.receive_message(QueueUrl=queue_url)["Messages"]
    assert [json.loads(message["Body"]) for message in messages] == [{"job_id": job_id}]


@pytest.mark.parametrize(
    "event,expected_status",
    [
        ({}, 400),
        ({"body": "not json"}, 400),
        ({"body": "[]"}, 400),
        ({"body": '{"payload": 42}'}, 400),
        ({"body": '{"payload": "\\ud800"}'}, 400),
        ({"body": "!", "isBase64Encoded": True}, 400),
        ({"body": json.dumps({"payload": "é" * (200 * 1024)})}, 413),
    ],
)
def test_invalid_submission_has_no_side_effects(submit, event, expected_status):
    handler, table, sqs, queue_url = submit

    assert handler(event, None)["statusCode"] == expected_status

    assert table.scan(Select="COUNT")["Count"] == 0
    assert "Messages" not in sqs.receive_message(QueueUrl=queue_url)


def test_failed_write_does_not_enqueue(submit):
    handler, table, sqs, queue_url = submit
    table.delete()

    assert handler({"body": '{"payload": "example"}'}, None)["statusCode"] == 503
    assert "Messages" not in sqs.receive_message(QueueUrl=queue_url)


def test_queue_rejection_marks_job_failed(submit):
    handler, table, sqs, queue_url = submit
    sqs.delete_queue(QueueUrl=queue_url)

    result = handler({"body": '{"payload": "example"}'}, None)

    assert result["statusCode"] == 503
    job_id = json.loads(result["body"])["job_id"]
    job = table.get_item(Key={"job_id": job_id})["Item"]
    assert job["status"] == "FAILED"
    assert job["error"] == "Queue rejected the job"


def test_unconfirmed_enqueue_keeps_job_pending(submit, monkeypatch):
    handler, table, _, queue_url = submit

    def timeout(**kwargs):
        raise ReadTimeoutError(endpoint_url=queue_url)

    monkeypatch.setattr(handler.__globals__["sqs"], "send_message", timeout)
    result = handler({"body": '{"payload": "example"}'}, None)

    assert result["statusCode"] == 503
    job_id = json.loads(result["body"])["job_id"]
    assert table.get_item(Key={"job_id": job_id})["Item"]["status"] == "PENDING"
