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
