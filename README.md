# Sales Visit Planning Platform

SVP is a microservice-based platform for field sales teams. Sales representatives use it to plan their daily customer visit routes, log visit and call outcomes in the field, and submit expense claims when the day is done. Managers review rep activity, approve or reject expense submissions, and flag customers as priority. Administrators manage user accounts.

The platform is built as a CA1 submission for the Advanced Microservices module. It demonstrates three distributed-systems patterns: the Saga pattern, the Transactional Outbox pattern, and CQRS.

---

## Architecture

The system is composed of four application services, an nginx reverse proxy, Apache Kafka, Redis, and three PostgreSQL databases. All components run as Docker containers under a single Compose stack.

### Services

| Service | Container name | Internal address | Responsibility |
|---|---|---|---|
| `customer_user_service` | `svp_mic-customer_user_service-1` | `customer_user_service:8000` | Customer records, user accounts, Redis cache, customer deactivation saga |
| `planning_service` | `planning_service` | `planning_service:8000` | Day plan lifecycle, saga orchestration, transactional outbox, CQRS projections |
| `expense_service` | `expense_service` | `expense_service:8000` | Expense submission and approval workflow, CQRS projections |
| `frontend_service` | `frontend_service` | `frontend_service:8000` | Jinja2 templates; no domain logic, no direct database access |

The nginx gateway (`nginx`, port `80`) is the single entry point for all external traffic. It strips the `/api` prefix from incoming requests and proxies by path prefix:

- `/api/customers` and `/api/users` → `customer_user_service:8000`
- `/api/plans` → `planning_service:8000`
- `/api/expenses` → `expense_service:8000`
- `/` → `frontend_service:8000`

### Infrastructure

| Component | Container name | Internal address |
|---|---|---|
| PostgreSQL (customers/users) | `customer_user_db` | `customer_user_db:5432` |
| PostgreSQL (planning) | `planning_db` | `planning_db:5432` |
| PostgreSQL (expenses) | `expense_db` | `expense_db:5432` |
| Apache Kafka | `kafka` | `kafka:9092` |
| Redis | `redis` | `redis:6379` |

### Database-per-service

Each backend service owns exactly one PostgreSQL instance and no other service can connect to it. There are no cross-service foreign keys. When `planning_service` needs to verify that a `rep_id` exists, it calls `customer_user_service` over HTTP. When it needs to know whether a customer is still active after a plan is confirmed, it receives a Kafka event rather than querying the customer database directly. This boundary prevents tight coupling at the data layer and means each service's schema can evolve independently.

---

## Patterns Implemented

### Saga

The Saga pattern manages distributed transactions that span multiple services by breaking them into a sequence of local transactions, each of which publishes an event that triggers the next step. If a step fails, compensating transactions undo the preceding steps.

Two sagas are implemented here.

**Plan confirmation saga.** When a rep confirms a day plan, `planning_service` transitions the plan from `draft` to `confirmed` and writes a `plan.confirmed` event to its transactional outbox in the same database transaction. The outbox poller picks this up and publishes it to Kafka. `customer_user_service` consumes the event, looks up each customer ID included in the payload, and checks whether every customer is still active. If any customer has been deactivated, `customer_user_service` publishes a `plan.rolled_back` event directly to Kafka. The planning service would then consume this to revert the plan (the rollback handler is in place in the consumer infrastructure).

**Customer deactivation saga.** When a customer is deactivated via `PATCH /api/customers/{id}/deactivate`, `customer_user_service` sets `is_active = False`, invalidates the Redis cache, and calls `publish_customer_deactivated` to send a `customer.deactivated` event directly to Kafka. `planning_service` consumes this event in `consumers/customer_events.py`. The handler finds every plan that references the deactivated customer in its visits or calls, filters to those in `confirmed` or `active` status, sets each back to `draft`, and writes a `plan.rolled_back` outbox row per plan — all within a single database transaction. The outbox poller then publishes those rollback events to Kafka.

### Transactional Outbox

The Transactional Outbox pattern solves the dual-write problem: without it, a service that writes to the database and then publishes to Kafka risks the Kafka publish failing after the database write has already committed, leaving downstream consumers with no event.

In `planning_service`, every state change that must produce a Kafka event writes the state update and an `Outbox` row in the same `db.commit()` call. The `Outbox` model stores the `event_type`, `aggregate_id`, a JSON `payload`, and a boolean `published` flag. Because both writes happen atomically, the event can never be lost — if the service crashes before the Kafka publish, the outbox row survives in the database.

A background task (`outbox/poller.py`) wakes every five seconds, queries for all rows where `published` is `False`, and attempts to publish each one by calling `publish_event`. On success it sets `published = True` and commits. On `OutboxPublishError` it logs the failure and leaves the row unpublished so it will be retried on the next poll cycle. Failures are per-row: one bad row does not block the others.

The atomic write is most clearly visible in `confirm_plan` in `plan_service.py`:

```python
plan.status = DayPlanStatus.confirmed
outbox_row = Outbox(
    event_type="plan.confirmed",
    aggregate_id=plan.id,
    payload={"plan_id": str(plan.id), "rep_id": str(plan.rep_id)},
)
db.add(outbox_row)
await db.commit()
```

The status change and the outbox insert land in the database together or not at all.

### CQRS

Command Query Responsibility Segregation separates the write model (state transitions driven by commands) from the read model (denormalised projections optimised for queries). The write tables hold normalised data with the full state machine; the read tables hold pre-computed summaries that can be served without joins or aggregation at query time.

Both `planning_service` and `expense_service` implement CQRS with synchronous projection updates.

In `planning_service`, every function that mutates a plan calls `update_plan_projection(plan_id, db)` immediately after committing the write. This function reads the current plan state and counts its visits and calls, then upserts a row in the `PlanReadModel` table. The read-side endpoints in `routers/plans_read.py` query only `PlanReadModel`; they never touch `DayPlan`, `Visit`, or `Call`.

In `expense_service`, every function that mutates an expense calls `update_expense_projection(expense_id, db)` after committing. This upserts a row in `ExpenseReadModel` with the current status, amount, category, and decision metadata. The read-side endpoints in `routers/expenses_read.py` query only `ExpenseReadModel`.

Because the projection is updated in the same request that performs the write, there is no propagation delay. Tests can assert read-model state immediately after a write without polling.

---

## Kafka Topics and Event Flows

| Topic | Produced by | Consumed by | Trigger |
|---|---|---|---|
| `plan.confirmed` | `planning_service` (via outbox) | `customer_user_service` | `PATCH /api/plans/{id}/confirm` transitions plan to `confirmed` |
| `plan.rolled_back` | `planning_service` (via outbox) | — | Consumer rolls back plans after `customer.deactivated` |
| `plan.rolled_back` | `customer_user_service` (direct) | — | Deactivated customer found on a confirmed plan during `plan.confirmed` validation |
| `customer.deactivated` | `customer_user_service` (direct) | `planning_service` | `PATCH /api/customers/{id}/deactivate` sets `is_active = False` |
| `expense.submitted` | `expense_service` | — | Expense created or resubmitted |
| `expense.decided` | `expense_service` | — | `approve_expense` or `reject_expense` completes |

---

## API Endpoints

All paths below are as seen from outside the stack (i.e. through nginx). The `/api` prefix is stripped before the request reaches the service.

### Customer User Service

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/customers` | List all active customers; served from Redis cache when available |
| `GET` | `/api/customers/{id}` | Fetch a single customer by UUID |
| `POST` | `/api/customers` | Create a new customer record |
| `PATCH` | `/api/customers/{id}` | Update customer name, address, or coordinates |
| `PATCH` | `/api/customers/{id}/deactivate` | Soft-delete a customer; publishes `customer.deactivated` |
| `PATCH` | `/api/customers/{id}/flag` | Set the priority flag (requires `X-User-Id` of a manager) |
| `PATCH` | `/api/customers/{id}/assign` | Assign a sales rep to a customer |
| `GET` | `/api/users` | List all user accounts |
| `GET` | `/api/users/{id}` | Fetch a single user by UUID |
| `POST` | `/api/users` | Create a new user account (password is bcrypt-hashed) |
| `PATCH` | `/api/users/{id}` | Update user name, email, or role |
| `DELETE` | `/api/users/{id}` | Hard-delete a user (requires `X-User-Id` of an administrator) |

### Planning Service

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/plans` | Create a day plan in `draft` state; validates that `rep_id` exists |
| `GET` | `/api/plans` | List all plans; accepts optional `?rep_id` query parameter |
| `GET` | `/api/plans/{id}` | Fetch a single plan by UUID |
| `PATCH` | `/api/plans/{id}/confirm` | Transition `draft` → `confirmed`; requires at least one visit or call |
| `PATCH` | `/api/plans/{id}/activate` | Transition `confirmed` → `active` |
| `PATCH` | `/api/plans/{id}/complete` | Transition `active` → `completed` |
| `POST` | `/api/plans/{id}/visits` | Add a customer visit to a plan |
| `POST` | `/api/plans/{id}/calls` | Add a customer call to a plan |
| `PATCH` | `/api/plans/{id}/visits/{vid}` | Update visit status and outcome notes |
| `PATCH` | `/api/plans/{id}/calls/{cid}` | Update call status and outcome notes |
| `GET` | `/api/plans/read/rep/{rep_id}` | Read-model: plan summaries for a specific rep |
| `GET` | `/api/plans/read/active` | Read-model: all plans currently in `active` status |
| `GET` | `/api/plans/read/history` | Read-model: full plan history; accepts `?rep_id` and `?date` |

### Expense Service

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/expenses` | Create an expense in `submitted` state |
| `GET` | `/api/expenses` | List all expenses; accepts optional `?rep_id` and `?status` |
| `GET` | `/api/expenses/{id}` | Fetch a single expense by UUID |
| `PATCH` | `/api/expenses/{id}/submit` | Transition `submitted` → `pending_approval` |
| `PATCH` | `/api/expenses/{id}/approve` | Transition `pending_approval` → `approved`; requires `manager_id` in body |
| `PATCH` | `/api/expenses/{id}/reject` | Transition `pending_approval` → `rejected`; requires `manager_id` in body |
| `PATCH` | `/api/expenses/{id}/resubmit` | Transition `rejected` → `submitted`; optionally amend amount, description, or receipt |
| `GET` | `/api/expenses/read/rep/{rep_id}` | Read-model: expense summaries for a specific rep |
| `GET` | `/api/expenses/read/status/{status}` | Read-model: expenses filtered by status string |
| `GET` | `/api/expenses/read/history` | Read-model: full expense history; accepts `?rep_id` and `?status` |

---

## Running the Stack

**Prerequisites:** Docker and Docker Compose.

Copy the example environment file and fill in the required values:

```bash
cp .env.example .env
```

The `.env` file must define database credentials for each service, the Kafka bootstrap server address, the Redis URL, and a Google Maps API key for geocoding. The services read these at startup via `env_file` in the Compose configuration.

Build and start the full stack:

```bash
docker compose up --build
```

All services wait for their dependencies to pass health checks before starting. PostgreSQL containers are checked with `pg_isready`, Kafka with `kafka-broker-api-versions`, and Redis with `redis-cli ping`. Once running, the nginx gateway is available at `http://localhost`. Each backend service also exposes interactive OpenAPI documentation at its internal port (`/docs`), reachable only from within the Docker network unless you add port mappings.

---

## Running the Tests

The integration test suite in `tests/` sends HTTP requests to the running Docker stack through nginx. The stack must be up before the tests are run.

Create a virtual environment and install the test dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install pytest httpx pytest-asyncio
```

Run all tests:

```bash
pytest tests/
```

Each test file is self-contained or uses function-scoped fixtures from `tests/conftest.py`. Fixtures create their own users, customers, and plans over HTTP so tests do not depend on pre-existing database state. Saga tests that trigger Kafka-driven rollbacks poll the plan endpoint with up to ten retries at 0.5-second intervals before asserting the final status.

---

## Directory Structure

The repository root contains `docker-compose.yml`, `.env.example`, `nginx/`, `shared/`, and one directory per service. The `shared/` package holds exception classes and the logger that all services import as a read-only volume mount; it has no dependencies on any individual service.

Each service directory follows the same layout: `main.py` wires the FastAPI app and registers startup/shutdown lifespan tasks; `models.py` holds the SQLAlchemy ORM definitions; `schemas.py` holds the Pydantic request and response models; `database.py` provides the async engine and session factory; and `routers/`, `services/`, `consumers/`, `producers/`, and `projections/` contain the domain logic, separated by concern. `planning_service` additionally contains `outbox/` for the poller and `alembic/` for database migrations. Each service has its own `alembic/` directory and `alembic.ini`.

The `tests/` directory at the project root contains the integration test suite with a shared `conftest.py` and one test file per domain area: `test_plans.py`, `test_expenses.py`, `test_cqrs.py`, `test_saga.py`, and `test_edge_cases.py`.
