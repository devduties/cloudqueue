import json
import runpy
from pathlib import Path
from uuid import uuid4

import boto3
import pytest
from moto import mock_aws


@pytest.fixture
def status_endpoint(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-north-1")
    with mock_aws():
        table = boto3.resource("dynamodb").create_table(
            TableName="jobs",
            KeySchema=[{"AttributeName": "job_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "job_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        monkeypatch.setenv("JOBS_TABLE_NAME", table.name)
        path = Path(__file__).resolve().parents[1] / "lambda" / "status_handler.py"
        yield runpy.run_path(str(path))["handler"], table


def test_returns_only_public_job_status(status_endpoint):
    handler, table = status_endpoint
    public_job = {
        "job_id": str(uuid4()),
        "status": "FAILED",
        "created_at": "2026-11-07T10:00:00+00:00",
        "updated_at": "2026-11-07T10:00:01+00:00",
    }
    table.put_item(Item={**public_job, "payload": "private", "error": "internal error"})

    result = handler({"pathParameters": {"job_id": public_job["job_id"]}}, None)

    assert result["statusCode"] == 200
    assert result["headers"]["Cache-Control"] == "no-store"
    assert json.loads(result["body"]) == public_job


@pytest.mark.parametrize("params", [None, {}, {"job_id": "bad-id"}, {"job_id": 1}])
def test_invalid_job_id_returns_bad_request(status_endpoint, params):
    handler, _ = status_endpoint

    result = handler({"pathParameters": params}, None)

    assert result["statusCode"] == 400


def test_missing_job_returns_not_found(status_endpoint):
    handler, _ = status_endpoint

    result = handler({"pathParameters": {"job_id": str(uuid4())}}, None)

    assert result["statusCode"] == 404
    assert json.loads(result["body"]) == {"error": "Job not found"}


def test_database_failure_returns_service_unavailable(status_endpoint):
    handler, table = status_endpoint
    table.delete()

    result = handler({"pathParameters": {"job_id": str(uuid4())}}, None)

    assert result["statusCode"] == 503
    assert json.loads(result["body"]) == {"error": "Could not read job status"}
