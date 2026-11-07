import json
import logging
import os
from uuid import UUID

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

config = Config(
    connect_timeout=2,
    read_timeout=2,
    retries={"mode": "standard", "total_max_attempts": 2},
)
jobs = boto3.resource("dynamodb", config=config).Table(os.environ["JOBS_TABLE_NAME"])


def response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
        "body": json.dumps(body),
    }


def handler(event, context):
    try:
        job_id = event["pathParameters"]["job_id"]
        if not isinstance(job_id, str):
            raise ValueError("Expected a string job ID")
        job_id = str(UUID(job_id))
    except (KeyError, TypeError, ValueError):
        return response(400, {"error": "job_id must be a valid UUID"})

    try:
        result = jobs.get_item(
            Key={"job_id": job_id},
            ConsistentRead=True,
            ProjectionExpression="job_id, #status, created_at, updated_at",
            ExpressionAttributeNames={"#status": "status"},
        )
    except (BotoCoreError, ClientError):
        logger.exception("Could not read status for job_id=%s", job_id)
        return response(503, {"error": "Could not read job status"})

    job = result.get("Item")
    if job is None:
        logger.info("Job not found job_id=%s", job_id)
        return response(404, {"error": "Job not found"})

    logger.info("Read status for job_id=%s", job_id)
    return response(200, job)
