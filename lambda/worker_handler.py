import json
import logging
import os
from datetime import UTC, datetime, timedelta
from time import sleep

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

WORK_ERROR = "Job processing failed"
# A worker times out before this claim expires. SQS retries after the claim expires.
CLAIM_DURATION = timedelta(seconds=60)
config = Config(
    connect_timeout=2,
    read_timeout=2,
    retries={"mode": "standard", "total_max_attempts": 2},
)
jobs = boto3.resource("dynamodb", config=config).Table(os.environ["JOBS_TABLE_NAME"])


def process_job(job_id, retry_count):
    key = {"job_id": job_id}
    now = datetime.now(UTC)
    claim = now.isoformat(timespec="microseconds")
    status = Attr("status")
    retryable_failure = status.eq("FAILED") & Attr("error").eq(WORK_ERROR)
    expired_claim = status.eq("PROCESSING") & Attr("updated_at").lte(
        (now - CLAIM_DURATION).isoformat(timespec="microseconds")
    )
    try:
        jobs.update_item(
            Key=key,
            ConditionExpression=status.eq("PENDING") | retryable_failure | expired_claim,
            UpdateExpression=(
                "SET #status = :processing, updated_at = :claim, retry_count = :retry_count "
                "REMOVE #error"
            ),
            ExpressionAttributeNames={"#status": "status", "#error": "error"},
            ExpressionAttributeValues={
                ":processing": "PROCESSING",
                ":claim": claim,
                ":retry_count": retry_count,
            },
        )
    except jobs.meta.client.exceptions.ConditionalCheckFailedException:
        job = jobs.get_item(Key=key, ConsistentRead=True).get("Item", {})
        terminal = job.get("status") == "DONE" or (
            job.get("status") == "FAILED" and job.get("error") != WORK_ERROR
        )
        logger.info("Skipping job_id=%s with status=%s", job_id, job.get("status"))
        return terminal

    logger.info("Processing job_id=%s", job_id)
    try:
        sleep(1)
    except Exception:
        logger.exception("Work failed for job_id=%s", job_id)
        finish_job(key, claim, "FAILED", error=WORK_ERROR)
        return False

    finish_job(key, claim, "DONE")
    logger.info("Completed job_id=%s", job_id)
    return True


def finish_job(key, claim, status, error=None):
    names = {"#status": "status"}
    values = {":status": status, ":now": datetime.now(UTC).isoformat()}
    update = "SET #status = :status, updated_at = :now"
    if error is not None:
        names["#error"] = "error"
        values[":error"] = error
        update += ", #error = :error"
    jobs.update_item(
        Key=key,
        ConditionExpression=Attr("status").eq("PROCESSING") & Attr("updated_at").eq(claim),
        UpdateExpression=update,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def handler(event, context):
    failures = []
    for record in event["Records"]:
        job_id = None
        try:
            job_id = json.loads(record["body"])["job_id"]
            if not isinstance(job_id, str) or not job_id:
                raise ValueError("Expected a job ID")
            receive_count = int(record.get("attributes", {}).get("ApproximateReceiveCount", "1"))
            if receive_count < 1:
                raise ValueError("Expected a positive SQS receive count")
            if process_job(job_id, receive_count - 1):
                continue
        except (BotoCoreError, ClientError, KeyError, TypeError, ValueError, RecursionError):
            logger.exception(
                "Could not process message_id=%s job_id=%s", record["messageId"], job_id
            )
        failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures}
