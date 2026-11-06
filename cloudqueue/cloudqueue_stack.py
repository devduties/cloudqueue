from pathlib import Path

from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_apigateway as apigateway
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_lambda as lambda_
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

        self.jobs_queue = sqs.Queue(
            self,
            "JobsQueue",
            encryption=sqs.QueueEncryption.SQS_MANAGED,
            removal_policy=RemovalPolicy.DESTROY,
        )
        submit_logs = logs.LogGroup(
            self,
            "SubmitJobLogs",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )
        submit_job = lambda_.Function(
            self,
            "SubmitJob",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="submit_handler.handler",
            code=lambda_.Code.from_asset(
                str(Path(__file__).resolve().parents[1] / "lambda"),
                exclude=["__pycache__", "**/__pycache__"],
            ),
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

        api = apigateway.RestApi(self, "JobsApi", cloud_watch_role=False)
        api.apply_removal_policy(RemovalPolicy.DESTROY)
        api.root.add_resource("jobs").add_method(
            "POST",
            apigateway.LambdaIntegration(submit_job),
            authorization_type=apigateway.AuthorizationType.NONE,
        )
