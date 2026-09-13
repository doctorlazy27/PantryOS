# Backend automation

## Setup

From `backend`:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DATABASE_URL = "postgresql+psycopg://user:password@host/database"
alembic upgrade head
```

`INTERNAL_JOB_SECRET` must be configured in the backend environment. It is never sent by the frontend.
Set `ENABLE_LOCAL_EXPIRY_LOOP=false` in production when AWS EventBridge is the scheduler. Leave it unset or set it to `true` for local development.

## Run the backend

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The in-process hourly expiry loop remains useful for local development. Production AWS scheduling should use the internal routes below instead.

## Manually trigger jobs locally

```powershell
$headers = @{ "X-Internal-Job-Secret" = $env:INTERNAL_JOB_SECRET }
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/internal/jobs/process-expiry" -Headers $headers
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/internal/jobs/process-inventory-intelligence" -Headers $headers
```

These endpoints are job triggers, not frontend APIs. Requests without the internal secret receive `401`.

## Run tests

```powershell
pytest -q
```

## AWS EventBridge Scheduler

Create two schedules that send authenticated `POST` requests:

- `/internal/jobs/process-expiry`
- `/internal/jobs/process-inventory-intelligence`

Send the secret as the `X-Internal-Job-Secret` header through a protected integration. Do not put the secret in Android or browser code. The jobs use PostgreSQL advisory transaction locks and deterministic database keys so repeated or overlapping invocations are safe.

Manager review endpoints:

- `GET /inventory/recommendations`
- `PATCH /inventory/recommendations/{recommendation_id}/approve`
- `PATCH /inventory/recommendations/{recommendation_id}/reject`
- `PATCH /inventory/recommendations/{recommendation_id}/complete`
