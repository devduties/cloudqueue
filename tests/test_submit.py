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


def test_submitted_job_status_through_worker_retry(submit, monkeypatch):
    submit_job, table, sqs, queue_url = submit
    handlers = Path(__file__).resolve().parents[1] / "lambda"
    worker = runpy.run_path(str(handlers / "worker_handler.py"))["handler"]
    status = runpy.run_path(str(handlers / "status_handler.py"))["handler"]

    def receive():
        message = sqs.receive_message(
            QueueUrl=queue_url,
            AttributeNames=["ApproximateReceiveCount"],
            VisibilityTimeout=0,
        )["Messages"][0]
        return {
            "messageId": message["MessageId"],
            "body": message["Body"],
            "attributes": message["Attributes"],
        }

    def fail_work(seconds):
        raise RuntimeError("simulated work failure")

    submitted = submit_job({"body": '{"payload": "example"}'}, None)
    assert submitted["statusCode"] == 202
    job_id = json.loads(submitted["body"])["job_id"]
    request = {"pathParameters": {"job_id": job_id}}
    pending = status(request, None)
    assert pending["statusCode"] == 200
    assert json.loads(pending["body"])["status"] == "PENDING"

    first = receive()
    with monkeypatch.context() as patch:
        patch.setitem(worker.__globals__, "sleep", fail_work)
        assert worker({"Records": [first]}, None) == {
            "batchItemFailures": [{"itemIdentifier": first["messageId"]}]
        }
    failed = status(request, None)
    assert failed["statusCode"] == 200
    assert json.loads(failed["body"])["status"] == "FAILED"
    assert "error" not in json.loads(failed["body"])

    monkeypatch.setitem(worker.__globals__, "sleep", lambda seconds: None)
    retry = receive()
    assert retry["messageId"] == first["messageId"]
    assert worker({"Records": [retry]}, None) == {"batchItemFailures": []}
    done = status(request, None)
    assert done["statusCode"] == 200
    assert json.loads(done["body"])["status"] == "DONE"
    assert table.get_item(Key={"job_id": job_id})["Item"]["retry_count"] == 1


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
