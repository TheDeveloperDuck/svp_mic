# Sales Visit Planning Platform

A microservice-based platform for field sales representatives to plan daily customer visits, log outcomes, and submit expenses. Managers oversee rep activity, approve expenses, and flag priority customers. Administrators manage user accounts.

Built for the Advanced Microservices CA1 — demonstrating Saga, Transactional Outbox, and CQRS patterns.

---

## Services

| Service | Port | Responsibility |
|---|---|---|
| `customer_user_service` | 8001 | Customer records, coordinates, user accounts, Redis cache |
| `planning_service` | 8002 | Day plan lifecycle, saga orchestration, outbox, Google Maps, CQRS |
| `expense_service` | 8003 | Receipt storage, submission and approval workflow, CQRS |
| `frontend_service` | 8000 | Jinja2 UI — no domain logic |

Each service has its own PostgreSQL database. No shared databases.

---

## Running the System

**Prerequisites:** Docker and Docker Compose.

```bash
# Copy and fill in required environment variables
cp .env.example .env

# Build and start all services
docker-compose up --build
```

Services wait for their dependencies (PostgreSQL, Kafka, Redis) to be healthy before starting.

The frontend is available at `http://localhost:8000`.

Interactive API docs for each backend service:

- Customer & User: `http://localhost:8001/docs`
- Planning: `http://localhost:8002/docs`
- Expense: `http://localhost:8003/docs`

---

## Environment Variables

Create a `.env` file at the project root. Required variables:

```
GOOGLE_MAPS_API_KEY=<your_key>

CUSTOMER_USER_DB_URL=postgresql+asyncpg://user:password@customer-db:5432/customer_user_db
PLANNING_DB_URL=postgresql+asyncpg://user:password@planning-db:5432/planning_db
EXPENSE_DB_URL=postgresql+asyncpg://user:password@expense-db:5432/expense_db

KAFKA_BOOTSTRAP_SERVERS=kafka:9092
REDIS_URL=redis://redis:6379
```

---

## Architecture

### Distributed Patterns

**Saga — Plan Confirmation Flow**

When a rep confirms a day plan, the Planning service runs a multi-step saga:

1. Validate the plan has at least one visit or call scheduled
2. For any customer without stored coordinates, call the Google Maps API and cache the result back to the Customer & User service
3. Run internal route optimisation across visit customers
4. Transition the plan from Draft → Confirmed

If the Google Maps API is unreachable, the plan stays in Draft and the rep is notified. If a customer is deactivated while on a confirmed or active plan, the Customer & User service publishes a `customer.deactivated` event, the Planning service flags the affected stop, and the rep is notified. The plan is not automatically cancelled — the rep decides how to respond.

**Transactional Outbox — Planning Service**

When a plan changes state, the Planning service writes the new state and an outbox event row in the same database transaction. A separate poller reads unpublished rows and publishes them to Kafka, then marks them as published. This prevents the dual-write problem where the DB write succeeds but the Kafka publish fails.

**CQRS — Planning and Expense Services**

Both services maintain separate read and write models:

- Write model handles state transitions (confirm plan, submit expense, approve/reject expense)
- Read model serves optimised projections (manager dashboard, rep expense history filtered by status or date)
- Read models are kept in sync via Kafka events

### Kafka Topics

| Topic | Published by | Purpose |
|---|---|---|
| `plan.confirmed` | Planning | Downstream notification of confirmed plan |
| `plan.rolled_back` | Planning | Plan returned to Draft (saga compensation) |
| `customer.deactivated` | Customer & User | Triggers Planning to flag affected stops |
| `expense.submitted` | Expense | Updates manager read model |
| `expense.decided` | Expense | Notifies rep of approval or rejection |

### State Machines

| Entity | States |
|---|---|
| Day Plan | Draft → Confirmed → Active |
| Visit | Planned → In Progress → Completed / Missed / Rescheduled |
| Call | Scheduled → Attempted → Completed |
| Expense | Submitted → Pending Approval → Approved / Rejected |

Rejected expenses can be amended and resubmitted, returning to Submitted.

### Business Rules

- A plan cannot be confirmed without at least one visit or call scheduled
- A visit cannot be marked complete without outcome notes
- Only a Manager can approve or reject an expense submission
- Historical records are retained when a rep account is removed

---

## Testing the APIs

With the system running, use the `/docs` endpoint for each service to make requests interactively, or use curl:

```bash
# Get active customer list
curl http://localhost:8001/customers

# Create a draft plan
curl -X POST http://localhost:8002/plans \
  -H "Content-Type: application/json" \
  -d '{"rep_id": 1, "date": "2026-04-07"}'

# Confirm a plan (triggers the saga)
curl -X POST http://localhost:8002/plans/1/confirm

# Submit an expense
curl -X POST http://localhost:8003/expenses \
  -H "Content-Type: application/json" \
  -d '{"plan_id": 1, "category": "fuel", "amount": 45.00, "receipt": "<base64>"}'

# Approve an expense (manager only)
curl -X POST http://localhost:8003/expenses/1/decide \
  -H "Content-Type: application/json" \
  -d '{"decision": "approved", "manager_id": 2}'
```

---

## Project Structure

```
svp_mic/
  docker-compose.yml
  .env.example
  customer_user_service/
  planning_service/
  expense_service/
  frontend_service/
  prompts.md          # AI prompt log (required by spec)
```

Each service follows the layout:

```
service_name/
  main.py
  models.py       # SQLAlchemy ORM models
  schemas.py      # Pydantic request/response models
  database.py     # async engine and session factory
  routers/
  consumers/      # aiokafka consumers
  producers/      # aiokafka producers (write to outbox first)
  Dockerfile
```

---

## Tech Stack

- **Python 3.11** + **FastAPI** — all services
- **PostgreSQL** — one database per service
- **Kafka** + **aiokafka** — async event communication
- **Redis** — active customer list cache
- **SQLAlchemy async** + **Alembic** — ORM and migrations
- **Jinja2** — frontend templates
- **Docker Compose** — local orchestration
