# CloudQueue — Async Job Queue on AWS
> Serverless job queue: submit a job, process it async, poll for status.
> Stack: API Gateway → Lambda → SQS → Lambda → DynamoDB. Infra in CDK (Python).

---

## Milestone Map

```
M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8 → M9
```

| # | Milestone | What ships | Commit target |
|---|-----------|-----------|---------------|
| 1 | Repo + CDK scaffold | Empty CDK app, venv, .gitignore, README stub | 1 |
| 2 | DynamoDB table | Jobs table (PK: job_id), CDK stack, cdk synth passes | 1 |
| 3 | Submit endpoint | POST /jobs → API Gateway → Lambda → SQS enqueue → write job row (PENDING) | 1 |
| 4 | Worker Lambda | SQS trigger → Lambda → fake work (sleep) → update row (PROCESSING → DONE/FAILED) | 1 |
| 5 | Status endpoint | GET /jobs/{id} → Lambda → DynamoDB read → return status JSON | 1 |
| 6 | Error handling | Dead-letter queue, failed jobs marked FAILED, retry count stored | 1 |
| 7 | Auth (API key) | API Gateway usage plan + API key, key required on POST and GET | 1 |
| 8 | Tests | pytest: unit tests for each Lambda handler (moto mocks) | 1 |
| 9 | README + diagram | Architecture diagram, one-command deploy instructions, badge | 1 |

---

## Architecture

```
Client
  │
  ▼
API Gateway (REST)
  ├── POST /jobs ──────────────► Submit Lambda
  │                                   │
  │                               SQS Queue ──► (DLQ on failure)
  │                                   │
  │                               Worker Lambda
  │                                   │
  └── GET /jobs/{id} ─────────► Status Lambda
                                       │
                               DynamoDB (jobs table)
```

---

## Stack choices

| Decision | Choice |
|----------|--------|
| Language | Python |
| IaC | CDK (Python) |
| Compute | Lambda |
| Queue | SQS |
| Database | DynamoDB |
| Auth | API Gateway API key |

---

## Milestone detail

### M1 — Repo + CDK scaffold
- `cdk init app --language python` inside `cloudqueue/`
- Set up venv, install `aws-cdk-lib`
- `.gitignore` covers `cdk.out/`, `__pycache__/`, `.env`
- Push empty scaffold — first real commit

### M2 — DynamoDB table
- Define `JobsTable` in CDK stack: PK `job_id` (String), billing PAY_PER_REQUEST
- `cdk synth` must pass clean
- No Lambda yet

### M3 — Submit endpoint
- Lambda: `submit_handler.py` — receives POST body `{ "payload": ... }`, generates UUID job_id, writes row `{ job_id, status: PENDING, created_at }`, enqueues to SQS
- CDK wires: API Gateway POST /jobs → Lambda → SQS → DynamoDB write IAM grants
- Return `{ job_id, status: "PENDING" }`

### M4 — Worker Lambda
- Lambda: `worker_handler.py` — triggered by SQS, reads message, simulates work (sleep 1s), updates DynamoDB row to DONE
- CDK wires: SQS event source mapping on worker Lambda
- On exception: update row to FAILED, let SQS retry → DLQ

### M5 — Status endpoint
- Lambda: `status_handler.py` — GET /jobs/{id}, reads DynamoDB, returns full job row
- 404 if job not found

### M6 — Error handling
- Add DLQ to CDK stack (SQS queue, `deadLetterQueue` on main queue)
- Worker catches exceptions, writes `error_message` to DynamoDB row
- `maxReceiveCount: 3` before DLQ

### M7 — Auth
- API Gateway usage plan + API key
- Both POST /jobs and GET /jobs/{id} require `x-api-key` header
- Document key retrieval in README

### M8 — Tests
- `pytest` + `moto` (AWS mock library)
- One test per Lambda: happy path + failure path
- Tests run locally with no real AWS calls

### M9 — README + diagram
- Architecture diagram (ASCII or draw.io export)
- `cdk deploy` instructions
- GitHub topics: `aws`, `serverless`, `cdk`, `sqs`, `lambda`, `python`
- CI badge (GitHub Actions: synth + test on push)

---

## Daily pace (one feature per day)

| Day | Milestone |
|-----|-----------|
| 1 | M1 + M2 |
| 2 | M3 |
| 3 | M4 |
| 4 | M5 + M6 |
| 5 | M7 |
| 6 | M8 |
| 7 | M9 + deploy |
