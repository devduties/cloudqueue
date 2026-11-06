# CloudQueue

CloudQueue is a serverless job queue built with Python and AWS CDK. The goal is to let clients
submit work, let a worker process it in the background, and let clients check its status later.

## Local setup

Install Python 3.12 and Node.js 22 with npm. Install the AWS CDK CLI globally once:

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

On macOS or Linux, activate the virtual environment with `source .venv/bin/activate`.
Synthesis writes the CloudFormation template to `cdk.out/` and runs without deploying resources.
For future deployment, select an AWS CLI profile that targets your project's assigned Region.

## Job submission

`POST /jobs` takes a JSON body such as `{"payload": "example"}` and returns HTTP `202`
with the job ID and `PENDING` status. M3 accepts unsigned requests. API key support is planned
for M7. The payload can contain up to 399 KiB of UTF-8 text.

The SQS worker claims queued jobs, simulates one second of work, and updates their status to
`DONE`. If processing fails, the worker records `FAILED` and returns the message for retry.

Run the submission and worker tests from the activated virtual environment:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
```
