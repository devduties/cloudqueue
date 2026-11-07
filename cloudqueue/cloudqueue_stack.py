from pathlib import Path

from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_apigateway as apigateway
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_lambda_event_sources as event_sources
from aws_cdk import aws_logs as logs
from aws_cdk import aws_sqs as sqs
from constructs import Construct


class CloudQueueStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.jobs_table = dynamodb.Table(
            self,
            "JobsTable",
            partition_key=dynamodb.Attribute(name="job_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        jobs_dlq = sqs.Queue(
            self,
            "JobsDeadLetterQueue",
            encryption=sqs.QueueEncryption.SQS_MANAGED,
            retention_period=Duration.days(14),
            removal_policy=RemovalPolicy.DESTROY,
        )
        self.jobs_queue = sqs.Queue(
            self,
            "JobsQueue",
            encryption=sqs.QueueEncryption.SQS_MANAGED,
            visibility_timeout=Duration.seconds(90),
            dead_letter_queue=sqs.DeadLetterQueue(queue=jobs_dlq, max_receive_count=3),
            removal_policy=RemovalPolicy.DESTROY,
        )
        submit_logs = logs.LogGroup(
            self,
            "SubmitJobLogs",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )
        lambda_code = lambda_.Code.from_asset(
            str(Path(__file__).resolve().parents[1] / "lambda"),
            exclude=["__pycache__", "**/__pycache__"],
        )
        submit_job = lambda_.Function(
            self,
            "SubmitJob",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="submit_handler.handler",
            code=lambda_code,
            timeout=Duration.seconds(20),
            log_group=submit_logs,
            environment={
                "JOBS_TABLE_NAME": self.jobs_table.table_name,
                "JOBS_QUEUE_URL": self.jobs_queue.queue_url,
            },
        )
        submit_job.apply_removal_policy(RemovalPolicy.DESTROY)
        self.jobs_table.grant(submit_job, "dynamodb:PutItem", "dynamodb:UpdateItem")
        self.jobs_queue.grant(submit_job, "sqs:SendMessage")

        worker_logs = logs.LogGroup(
            self,
            "WorkerLogs",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )
        worker = lambda_.Function(
            self,
            "Worker",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="worker_handler.handler",
            code=lambda_code,
            timeout=Duration.seconds(15),
            log_group=worker_logs,
            environment={"JOBS_TABLE_NAME": self.jobs_table.table_name},
        )
        worker.apply_removal_policy(RemovalPolicy.DESTROY)
        self.jobs_table.grant(worker, "dynamodb:GetItem", "dynamodb:UpdateItem")
        worker.add_event_source(
            event_sources.SqsEventSource(
                self.jobs_queue,
                batch_size=1,
                report_batch_item_failures=True,
            )
        )

        api = apigateway.RestApi(self, "JobsApi", cloud_watch_role=False)
        api.apply_removal_policy(RemovalPolicy.DESTROY)
        jobs_resource = api.root.add_resource("jobs")
        jobs_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(submit_job),
            authorization_type=apigateway.AuthorizationType.NONE,
        )

        status_logs = logs.LogGroup(
            self,
            "JobStatusLogs",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )
        job_status = lambda_.Function(
            self,
            "JobStatus",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="status_handler.handler",
            code=lambda_code,
            timeout=Duration.seconds(15),
            log_group=status_logs,
            environment={"JOBS_TABLE_NAME": self.jobs_table.table_name},
        )
        job_status.apply_removal_policy(RemovalPolicy.DESTROY)
        self.jobs_table.grant(job_status, "dynamodb:GetItem")
        jobs_resource.add_resource("{job_id}").add_method(
            "GET",
            apigateway.LambdaIntegration(job_status),
            authorization_type=apigateway.AuthorizationType.NONE,
        )
