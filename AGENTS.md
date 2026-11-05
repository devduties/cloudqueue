# CloudQueue — Agent Rules

These rules apply to every coding assistant working in this project.
Read this file before writing any code.

---

## Project identity

- **Name:** CloudQueue
- **Purpose:** Serverless async job queue on AWS — portfolio project
- **Stack:** Python · AWS CDK (Python) · Lambda · SQS · DynamoDB · API Gateway
- **Goal:** Clean, deployable, well-tested code a hiring panel can read

---

## Hard rules

### AWS
- All resources go in the project's assigned AWS Region — NEVER hardcode `us-east-1` or any other region; read region from CDK environment or environment variable
- NEVER use Lambda@Edge
- NEVER attempt cross-region replication or multi-region resources
- NEVER use CloudFormation StackSets
- Use `PAY_PER_REQUEST` billing on DynamoDB (no provisioned capacity)
- Set `removalPolicy: DESTROY` on all resources — this is a dev/portfolio project, not production

### CDK
- Always run `cdk synth --strict` before `cdk deploy`
- Always run `cdk diff` before `cdk deploy` — show the diff, never skip it
- NEVER use `--hotswap` or `--express` flags in deploy instructions — they create drift and hide errors
- Use L2 constructs (e.g. `aws_lambda.Function`, `aws_sqs.Queue`) — avoid raw CloudFormation (L1) unless L2 cannot do it
- Use `grant_*()` methods for IAM permissions between resources — never write inline IAM policy JSON
- Commit `cdk.context.json` — do not `.gitignore` it

### Python
- Pin all dependencies in `requirements.txt` with exact versions (e.g. `aws-cdk-lib==2.x.x`)
- Use a virtualenv — document activation in README
- Use `python-dotenv` for local env vars if needed; never hardcode values
- Follow PEP 8; max line length 100
- No `print()` in Lambda handlers — use `import logging; logger = logging.getLogger()`

### Lambda handlers
- Each handler lives in `lambda/` as its own file: `submit_handler.py`, `worker_handler.py`, `status_handler.py`
- Each handler has a `handler(event, context)` entry point
- Return proper HTTP status codes and JSON bodies in all responses
- Always handle missing/malformed input with a 400 response, not an unhandled exception
- Log the `job_id` on every operation

### Testing
- Tests live in `tests/`
- Use `pytest` + `moto` for AWS mocks — no real AWS calls in tests
- One test file per Lambda: `test_submit.py`, `test_worker.py`, `test_status.py`
- Each file has at minimum: one happy-path test and one failure/error test

---

## Soft rules (follow unless there is a good reason not to)

- One commit per milestone — keep commits meaningful
- Keep CDK stack in one file (`cloudqueue/cloudqueue_stack.py`) until it grows past ~150 lines
- Keep Lambda handlers under 80 lines each — extract helpers if needed
- README explains what the project does in plain language (no jargon), with a diagram

---

## Project layout

```
cloudqueue/
├── app.py                        # CDK app entry point
├── cdk.json
├── cdk.context.json              # committed
├── requirements.txt              # CDK + app deps, pinned
├── cloudqueue/
│   └── cloudqueue_stack.py       # all AWS resources defined here
├── lambda/
│   ├── submit_handler.py
│   ├── worker_handler.py
│   └── status_handler.py
├── tests/
│   ├── test_submit.py
│   ├── test_worker.py
│   └── test_status.py
├── ROADMAP.md
├── AGENTS.md                     # this file
└── README.md
```

---

## Job schema (DynamoDB)

```
{
  "job_id":      "uuid4 string — partition key",
  "status":      "PENDING | PROCESSING | DONE | FAILED",
  "payload":     "string — raw input from caller",
  "created_at":  "ISO 8601 UTC string",
  "updated_at":  "ISO 8601 UTC string",
  "error":       "string — only present on FAILED"
}
```

---

## API contract

### POST /jobs
Request:
```json
{ "payload": "any string" }
```
Response 202:
```json
{ "job_id": "uuid", "status": "PENDING" }
```

### GET /jobs/{job_id}
Response 200:
```json
{ "job_id": "uuid", "status": "DONE", "created_at": "...", "updated_at": "..." }
```
Response 404:
```json
{ "error": "Job not found" }
```

Both endpoints require header: `x-api-key: <key>`

---

## Environment variables (Lambda runtime)

| Variable | Set by | Used in |
|----------|--------|---------|
| `JOBS_TABLE_NAME` | CDK (env on Function) | all handlers |
| `JOBS_QUEUE_URL` | CDK (env on Function) | submit_handler |

Never hardcode table names or queue URLs in handler code.

---

## What NOT to do

- Do not add features outside the roadmap milestones without asking
- Do not introduce new AWS services not listed in the stack (no Step Functions, no SNS, no Cognito) without discussing first
- Do not write CloudFormation YAML — everything goes through CDK Python
- Do not use `aws-cdk` v1 import paths — use `aws_cdk` (v2)
- Do not leave TODO comments in committed code — finish the thing or open a GitHub issue
