# CloudQueue

CloudQueue is a serverless job queue built with Python and AWS CDK. The goal is to let clients
submit work, let a worker process it in the background, and let clients check its status later.
See [ROADMAP.md](ROADMAP.md) for the implementation milestones.

## Local setup

Install Python 3.12, Node.js 22, and pnpm. From the project directory in PowerShell, run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
pnpm install --frozen-lockfile
pnpm exec cdk synth --strict --no-lookups
```

On macOS or Linux, activate the virtual environment with `source .venv/bin/activate`.
Synthesis writes the CloudFormation template to `cdk.out/` and runs without deploying resources.
For future deployment, select an AWS CLI profile that targets your project's assigned Region.
