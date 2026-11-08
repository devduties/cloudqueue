# CloudQueue

[![CI](https://github.com/devduties/cloudqueue/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/devduties/cloudqueue/actions/workflows/ci.yml)

CloudQueue is a serverless job queue built with Python and AWS CDK. Clients submit work,
a worker processes it in the background, and clients can check its status later.

## Architecture

```text
Client (x-api-key) -> API Gateway
  POST /jobs          -> Submit Lambda -> DynamoDB (write job)
                                       -> SQS jobs queue -> Worker Lambda
                                              |                   |
                                              v                   v
                                        Dead-letter queue   DynamoDB (update status)
  GET /jobs/{job_id}  -> Status Lambda -> DynamoDB (read status)
```

## Local setup

Install Python 3.12 and Node.js 22. Install the AWS CDK CLI globally once:

```powershell
npm install --global aws-cdk@2.1148.0
```

From the project directory in PowerShell, activate the Python virtual environment and synthesize:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
cdk synth --strict --no-lookups
```

On macOS or Linux, activate the virtual environment with ``source .venv/bin/activate``.

## Deploy

Confirm your AWS Region in AWS Settings under **View all projects → Overview →
Additional Info → Region**. Run this once per account before your first deploy:

```powershell
cdk bootstrap --profile my-profile
```

Then synthesize, review the diff, and deploy:

```powershell
cdk synth --strict --no-lookups --profile my-profile
cdk diff --profile my-profile
cdk deploy --profile my-profile
```

## Job submission

``POST /jobs`` takes a JSON body such as ``{"payload": "example"}`` and returns HTTP ``202``
with the job ID and ``PENDING`` status. The payload can contain up to 399 KiB of UTF-8 text.

The worker claims queued jobs and marks them ``DONE`` when processing succeeds. If processing
fails, the worker records ``FAILED`` and returns the message for retry. Jobs that fail three
times are moved to a dead-letter queue.

Poll ``GET /jobs/{job_id}`` for the job ID, current status, and timestamps. A valid ID with no
matching job returns HTTP ``404``.

Both routes require the ``x-api-key`` header. After deploying, find ``JobsApiKeyId`` in the
stack outputs. In the API Gateway console, open **API keys** and select that ID to reveal
the key value. Send the value in ``x-api-key`` and keep it out of source control.

Anyone with the shared key can call either route.

Run the tests from the activated virtual environment:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
```
