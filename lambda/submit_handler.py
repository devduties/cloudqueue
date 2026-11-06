import base64
import json
import logging
import os
from datetime import UTC, datetime
from uuid import uuid4

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Leave room for the job metadata within DynamoDB's 400 KiB item limit.
MAX_PAYLOAD_BYTES = 399 * 1024
config = Config(
    connect_timeout=2,
    read_timeout=2,
    retries={"mode": "standard", "total_max_attempts": 2},
)
jobs = boto3.resource("dynamodb", config=config).Table(os.environ["JOBS_TABLE_NAME"])
sqs = boto3.client("sqs", config=config)
queue_url = os.environ["JOBS_QUEUE_URL"]


def response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def mark_enqueue_failed(job_id):
    try:
        jobs.update_item(
            Key={"job_id": job_id},
            ConditionExpression=Attr("status").eq("PENDING"),
            UpdateExpression="SET #status = :failed, updated_at = :now, #error = :error",
            ExpressionAttributeNames={"#status": "status", "#error": "error"},
            ExpressionAttributeValues={
                ":failed": "FAILED",
                ":now": datetime.now(UTC).isoformat(),
                ":error": "Queue rejected the job",
            },
        )
    except (BotoCoreError, ClientError):
        logger.exception("Could not mark job_id=%s as failed", job_id)


def handler(event, context):
    try:
        body = event["body"]
        if event.get("isBase64Encoded"):
            body = base64.b64decode(body, validate=True)
        payload = json.loads(body)["payload"]
        if not isinstance(payload, str):
            return response(400, {"error": "payload must be a string"})
        payload_size = len(payload.encode("utf-8"))
    except (KeyError, TypeError, ValueError, RecursionError):
        return response(400, {"error": "Expected a JSON object with a string payload"})

    if payload_size > MAX_PAYLOAD_BYTES:
        return response(413, {"error": "payload exceeds 399 KiB"})

    job_id = str(uuid4())
    timestamp = datetime.now(UTC).isoformat()
    job = {
        "job_id": job_id,
        "status": "PENDING",
        "payload": payload,
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    try:
        jobs.put_item(Item=job, ConditionExpression=Attr("job_id").not_exists())
    except (BotoCoreError, ClientError):
        logger.exception("Could not save job_id=%s", job_id)
        return response(503, {"error": "Could not save job"})

    try:
        sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps({"job_id": job_id}))
    except (BotoCoreError, ClientError) as error:
        logger.exception("Could not confirm enqueue for job_id=%s", job_id)
        # A timeout or server error can occur after SQS accepts the message.
        if isinstance(error, ClientError):
            metadata = error.response.get("ResponseMetadata", {})
            status = metadata.get("HTTPStatusCode", 0)
            if 400 <= status < 500 and not metadata.get("RetryAttempts"):
                mark_enqueue_failed(job_id)
        return response(503, {"job_id": job_id, "error": "Could not enqueue job"})

    logger.info("Accepted job_id=%s", job_id)
    return response(202, {"job_id": job_id, "status": "PENDING"})
