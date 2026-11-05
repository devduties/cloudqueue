import os

import aws_cdk as cdk

from cloudqueue.cloudqueue_stack import CloudQueueStack


app = cdk.App()
CloudQueueStack(
    app,
    "CloudQueueStack",
    env=cdk.Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"),
        region=os.getenv("CDK_DEFAULT_REGION"),
    ),
)
app.synth()
