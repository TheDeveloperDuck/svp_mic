# SVP Design Analysis

Codebase scan conducted 2026-05-09. All file references are relative to the project root.

---

## 1. ARCHITECTURE

### Services and responsibilities

| Service | Primary responsibility | Port |
|---|---|---|
| `customer_user_service` | Owns User and Customer records; manages the customer lifecycle (creation, deactivation, priority flagging, rep assignment); Redis cache of active customers; bcrypt authentication seed data | 8000 |
| `planning_service` | Owns DayPlan, Visit, Call, Outbox, and PlanReadModel; enforces plan lifecycle (draft → confirmed → active → completed); transactional outbox; CQRS read model | 8000 |
| `expense_service` | Owns ExpenseSubmission and ExpenseReadModel; enforces expense lifecycle (submitted → pending_approval → approved / rejected); CQRS read model | 8000 |
| `frontend_service` | Jinja2 server-side rendering; fetches data from backend services via Nginx; no own database | 8000 |
| Nginx | HTTP reverse proxy; routes `/api/customers` and `/api/users` to `customer_user_service`, `/api/plans` to `planning_service`, `/api/expenses` to `expense_service`, `/` to `frontend_service`; strips the `/api` prefix before proxying (`nginx/nginx.conf`, lines 21–48) | 80 |

### Inter-service communication

**Synchronous HTTP:**
- `planning_service/services/plan_service.py`, lines 57–60: `create_plan()` calls `http://customer_user_service:8000/users/{rep_id}` to validate the sales rep exists before creating a plan.
- `frontend_service/routers/pages.py`, lines 57–64: `_get()` helper calls Nginx (`http://nginx/api/...`) for every page render to fetch customers, plans, and expenses.

**Asynchronous Kafka events (five topics in use):**

| Topic | Produced by | Consumed by |
|---|---|---|
| `plan.confirmed` | `planning_service` outbox poller | `customer_user_service` (`plan_confirmed.py`) |
| `plan.rolled_back` | `customer_user_service` (`plan_confirmed.py`) and `planning_service` outbox poller | No consumer implemented |
| `customer.deactivated` | `customer_user_service` (`customer_deactivated.py`) | `planning_service` (`customer_events.py`) |
| `expense.submitted` | `expense_service` (`expense_events.py`) — function defined but **never called** (see §5) | — |
| `expense.decided` | `expense_service` (`expense_events.py`) | `expense_service` itself (`expense_decisions.py`) — handler only logs (see §5) |

**Redis:**
- `customer_user_service/routers/customers.py`, lines 43–44: global `redis.from_url()` client, key `active_customers`.
- Used exclusively for caching the full active-customer list on `GET /customers`. Write operations call `_invalidate_cache()` (line 162).

### Routing

Nginx in `nginx/nginx.conf` does prefix-based routing and strips `/api` before proxying. There is no authentication at the gateway layer. The Nginx `upstream` target is stored in a variable (`$upstream`) at lines 22, 28, 34, 40 to avoid the 502 issued when a backend is down at startup.

### Database ownership

Each backend service has an exclusive PostgreSQL database. No service holds a foreign key into another service's schema. Cross-service references (e.g. `rep_id` in `planning_service/models.py` line 80, `customer_id` in Visit line 148) are plain UUID columns with no referential integrity enforced at the database level. Data ownership is therefore enforced only at the application layer.

### Separation of services

Services are well-separated at the data layer (separate databases, no shared tables). Infrastructure is shared in that all services share the same Kafka broker and Zookeeper cluster. Redis is currently used only by `customer_user_service`.

---

## 2. BUSINESS RULES AND CONSISTENCY

### customer_user_service

| Rule | File | Function / location |
|---|---|---|
| Email must be unique per user | `routers/users.py` lines 184–188 (create) and 226–232 (update) | `create_user()`, `update_user()` |
| Password is bcrypt-hashed before storage | `routers/users.py` lines 117–125 | `_hash_password()` |
| Only a user with `manager` role may flag a customer as priority | `routers/customers.py` lines 118–159 | `_require_role(UserRole.manager)` |
| Only a user with `administrator` role may hard-delete a user | `routers/users.py` lines 77–113 | `_require_administrator()` |
| `X-User-Id` must be a valid UUID or 400 is returned | `routers/customers.py` lines 140–146, `routers/users.py` lines 99–104 | `_require_role()`, `_require_administrator()` |
| Assigning a rep requires the target user to have `sales_rep` role | `routers/customers.py` lines 404–414 | `assign_rep()` |
| Customer deactivation is a soft-delete (`is_active = False`) | `routers/customers.py` lines 309–347 | `deactivate_customer()` |
| Re-deactivating an already-inactive customer raises HTTP 409 | `routers/customers.py` lines 327–337 | `deactivate_customer()` |
| Customer deactivation triggers `customer.deactivated` Kafka event | `routers/customers.py` line 345 | `deactivate_customer()` → `publish_customer_deactivated()` |
| `CustomerPriorityFlag` audit row is created when a customer is flagged | `routers/customers.py` lines 371–376 | `flag_customer()` |

**Transactions:** Every router function calls `db.commit()` once after all mutations in that request. There are no savepoints. SQLAlchemy's async session is used throughout; each request gets its own session via the `get_db()` dependency (`database.py` lines 46–62).

**Consistency boundary:** `customer_user_service` is the aggregate root for both User and Customer. The `ManagerRep` junction table lives here too. No other service modifies these records.

### planning_service

| Rule | File | Function / location |
|---|---|---|
| A plan must have at least one visit or call to be confirmed | `services/plan_service.py` lines 129–139 | `confirm_plan()` |
| A visit cannot be marked complete without `outcome_notes` | `services/plan_service.py` lines 299–302 | `update_visit()` |
| Plan transitions follow strict sequence: draft → confirmed → active → completed | `services/plan_service.py` lines 124–127, 171–174, 200–203 | `confirm_plan()`, `activate_plan()`, `complete_plan()` |
| `rep_id` must refer to an existing user in `customer_user_service` | `services/plan_service.py` lines 57–62 | `create_plan()` — synchronous HTTP call |
| Plan confirmation writes an Outbox row atomically with the status change | `services/plan_service.py` lines 141–148 | `confirm_plan()` — single `db.commit()` covering both |
| Customer deactivation rolls back confirmed/active plans to draft | `consumers/customer_events.py` lines 114–130 | `_handle_customer_deactivated()` |
| Rollback writes `plan.rolled_back` Outbox rows in the same transaction | `consumers/customer_events.py` lines 116–123, 130 | `_handle_customer_deactivated()` |

**Transactions:** The atomic commit pairing plan status + Outbox row in `confirm_plan()` is the key consistency mechanism for the transactional outbox pattern. The customer-deactivation handler also commits all affected plan updates + Outbox rows in one `db.commit()` (line 130). The projection update (`update_plan_projection()`) issues a second separate `db.commit()` (line 97 in `plan_projection.py`) after the main commit.

**Aggregate root:** `DayPlan` acts as the root for `Visit`, `Call`, and `Outbox` rows. All mutations go through `plan_service.py`.

### expense_service

| Rule | File | Function / location |
|---|---|---|
| `manager_id` must be provided to approve or reject; absence raises `ExpenseApprovalError` | `services/expense_service.py` lines 156–159, 207–210 | `approve_expense()`, `reject_expense()` |
| Status transitions are strictly enforced | `services/expense_service.py` lines 121–125, 164–168, 215–219, 266–270 | All lifecycle functions |
| Only `amount`, `description`, and `receipt_image` may be amended on resubmission | `services/expense_service.py` lines 272–277 | `resubmit_expense()` |
| `decided_at` and `decided_by` are cleared on resubmission | `services/expense_service.py` lines 279–281 | `resubmit_expense()` |

**Transactions:** Each lifecycle function calls `db.commit()` once. Kafka publishing happens after the commit (lines 176–181, 227–232), outside the transaction — there is no outbox here (see §5).

**No cross-service FK validation for manager_id:** `approve_expense()` and `reject_expense()` accept `manager_id: UUID` but do not query `customer_user_service` to verify the UUID is a real manager. The role of the approver is entirely untested.

---

## 3. INTERNAL STRUCTURE (LAYERS)

### customer_user_service

```
main.py         — FastAPI wiring, lifespan, middleware
routers/        — HTTP handlers + inline business rules
models.py       — SQLAlchemy ORM (infrastructure + domain model)
schemas.py      — Pydantic I/O shapes
database.py     — engine + session factory
producers/      — Kafka event publishing
consumers/      — Kafka event consuming
```

There is no separate service layer. Business logic (role checks, deactivation guards, cache invalidation, Kafka event publishing) lives directly inside the router functions (`routers/customers.py` and `routers/users.py`). This is a flat two-layer arrangement: routes → database, with infrastructure concerns (Redis, Kafka) interspersed in the route layer.

The `_require_role()` factory (`routers/customers.py` lines 118–159) and `_require_administrator()` (`routers/users.py` lines 77–113) are inline FastAPI dependencies rather than a reusable auth layer. They duplicate the pattern of reading `X-User-Id`, parsing a UUID, querying the DB, and checking the role.

### planning_service

```
main.py               — FastAPI wiring, lifespan, background tasks
routers/plans.py      — HTTP routing and exception translation
routers/plans_read.py — Read-side HTTP endpoints (queries PlanReadModel)
services/plan_service.py — Business logic, state transitions, outbox writes
models.py             — ORM models
schemas.py            — Pydantic I/O shapes
database.py           — engine + session factory
outbox/poller.py      — Infrastructure: Kafka publishing loop
consumers/            — Infrastructure: Kafka event consuming
projections/          — Synchronous read-model update
producers/            — Kafka event publishing
```

This is the most layered service. The router delegates to `plan_service.py` for all decisions; the router's job is only to translate domain exceptions into HTTP status codes. Domain logic (`PlanConfirmationError`, `VisitCompletionError`, state guards) is centralised in `plan_service.py`. The outbox, projection, and consumer are separate modules.

The HTTP call to validate `rep_id` in `plan_service.create_plan()` (line 57) is an infrastructure concern — an HTTP client — inside the service layer. There is no repository interface; SQLAlchemy sessions are passed directly into service functions.

### expense_service

```
main.py                   — FastAPI wiring
routers/expenses.py       — HTTP routing + calls service layer
routers/expenses_read.py  — Read-side HTTP endpoints
services/expense_service.py — Business logic, state transitions
models.py                 — ORM models
schemas.py                — Pydantic I/O shapes
database.py               — engine + session factory
consumers/                — Kafka consumer (stub)
producers/expense_events.py — Kafka publishing (called inside service layer)
projections/              — Read-model update
```

Similar layering to `planning_service`. The router delegates to `expense_service.py`. The key difference is that Kafka publishing (`publish_expense_decided()`) is called directly inside `approve_expense()` and `reject_expense()`, outside any database transaction, without an outbox buffer.

### frontend_service

```
main.py        — FastAPI wiring, Jinja2 setup
routers/pages.py — All routes + HTTP aggregation logic inline
templates/     — Jinja2 HTML files
static/        — CSS / JS assets
```

No service layer exists. Each route function fetches data directly via `_get()` and passes it to a template. All application logic (URL construction, fallback to empty lists, B3 header forwarding) is in `pages.py`. The `templates` object is a module-level mutable global set by `main.py` after import, which is an uncommon coupling pattern (`pages.py` lines 32, `main.py` line 60).

### Dependency direction

In `planning_service` and `expense_service`, dependencies point inward: routers depend on service functions; service functions depend on ORM models and projections; infrastructure (Kafka, outbox poller) is a separate module. In `customer_user_service`, the router functions mix all concerns.

There are no ports-and-adapters abstractions anywhere. SQLAlchemy sessions, Kafka producers, and Redis clients are used directly without interface boundaries, making unit testing without real infrastructure difficult.

---

## 4. CROSS-CUTTING CONCERNS

### Logging

A single pre-configured `logging.Logger` named `"svp"` is defined in `shared/logger.py` (lines 14–24) and imported by every service. Level is hardcoded to `logging.DEBUG` (line 16), with a single `StreamHandler` writing to stderr. Format is `"%(asctime)s [%(levelname)s] %(message)s"` (line 17). No log level is configurable via environment variable. No structured/JSON logging. No correlation ID is injected into log records (the B3 trace-id is logged only as a plain string by the middleware in each `main.py`).

### Authentication and authorisation

There is no authentication. No JWT, no session cookie, no API key. The system's role enforcement mechanism is the `X-User-Id` header: the caller passes a UUID claiming to be a user, and the service queries its own database to check that user's role.

This means:
- Any client who knows (or guesses) a manager's UUID can call `PATCH /customers/{id}/flag` and flag a customer as priority.
- Any client who knows an administrator's UUID can call `DELETE /users/{id}` and hard-delete any user.
- The frontend service passes no credential at all when fetching data from backend services.

Role enforcement is duplicated in two separate dependency functions: `_require_role()` in `routers/customers.py` (lines 118–159) and `_require_administrator()` in `routers/users.py` (lines 77–113). Both implement the same `X-User-Id` → UUID parse → DB lookup → role check flow independently.

### Error handling

**Approach varies by layer and service:**

- `planning_service` routers catch domain exceptions (`PlanConfirmationError`, `VisitCompletionError`, `ValueError`) and map them to appropriate HTTP status codes (422, 409, 404). This is consistent across all endpoints in `routers/plans.py`.
- `customer_user_service` routers raise `HTTPException` directly inside router functions rather than using a domain exception type for most cases. The exception is `CustomerDeactivatedError`, which is caught in `deactivate_customer()` and converted to 409 (`routers/customers.py` lines 327–337).
- `expense_service` routers translate `ValueError` to 404/409 and `ExpenseApprovalError` to 422.
- Kafka consumer loops in all services wrap each message in a `try/except Exception` that logs and continues (e.g. `plan_confirmed.py` lines 184–189, `customer_events.py` lines 171–177). This prevents one bad message from killing the consumer but means a permanently malformed message is logged on every restart due to `auto_offset_reset="earliest"` with no dead-letter queue.
- `frontend_service` `_get()` (`pages.py` lines 57–64) catches any `httpx.HTTPError` and returns `[]`. Non-200 status codes that are not connection errors (e.g. 500 from a backend) are silently swallowed because `raise_for_status()` is called before the catch, which means HTTP 5xx errors are also caught and return `[]`.

### Retry logic and resilience

- The outbox poller in `planning_service/outbox/poller.py` provides at-least-once delivery retry for `plan.confirmed` and `plan.rolled_back` events. Failed publish attempts leave the row `published=False` and the poller retries every 5 seconds.
- There is no circuit breaker anywhere.
- The synchronous HTTP call from `planning_service` to `customer_user_service` in `plan_service.create_plan()` (lines 57–60) has no timeout set on the `httpx.AsyncClient`. A slow or hung `customer_user_service` will block plan creation indefinitely.
- Kafka producers in `customer_user_service` (`customer_deactivated.py`) and `expense_service` (`expense_events.py`) create a new `AIOKafkaProducer` per call, start it, publish, and stop it. This is connection-per-publish rather than a long-lived shared producer; there is no retry on the producer side.
- Redis errors in `customer_user_service` are caught and swallowed by `_read_cache()` and `_write_cache()` (`routers/customers.py` lines 175–205), allowing the service to degrade gracefully to direct DB reads.

### Configuration management

All services use `python-dotenv` to load `.env` from the project root. Environment variables configure database URLs, Kafka bootstrap servers, Kafka group IDs, and Redis URL. There are no config files beyond `.env`; there is no validation of env vars at startup. Several fallback defaults are hardcoded:
- `planning_service/consumers/customer_events.py` line 38: group ID `"planning_service"` is hardcoded, not from env.
- `frontend_service/routers/pages.py` line 36: `_NGINX_BASE = "http://nginx/api"` is hardcoded, not configurable.
- `planning_service/outbox/poller.py` line 18: `_POLL_INTERVAL_SECONDS = 5` is a module-level constant, not configurable.

### Observability

- **Health checks:** Every service exposes `GET /health` returning `{"status": "ok"}` (e.g. `customer_user_service/main.py` lines 75–83). These are liveness-only; they do not probe the database or Kafka connection.
- **Tracing:** B3 headers are extracted by `shared/tracing.py` and the `x-b3-traceid` is logged by middleware in each service's `main.py`. Headers are forwarded by the frontend to backends via `build_tracing_headers()`. There is no distributed tracing backend (Jaeger, Zipkin) configured in `docker-compose.yml`.
- **Metrics:** No Prometheus or similar metrics instrumentation.
- **Docker health checks:** `docker-compose.yml` defines health checks for each service using `curl -f http://localhost:8000/health`. Databases have `pg_isready` checks.

---

## 5. DESIGN WEAKNESSES

### W1 — plan.confirmed payload omits customer_ids; saga is inoperative
**File:** `planning_service/services/plan_service.py`, lines 142–146  
**File:** `customer_user_service/consumers/plan_confirmed.py`, line 93

The outbox payload written when a plan is confirmed is:
```python
payload={"plan_id": str(plan.id), "rep_id": str(plan.rep_id)}
```
No `customer_ids` field is included. The consumer in `customer_user_service` reads:
```python
customer_ids: list = data.get("customer_ids", [])
```
This always evaluates to `[]`. The deactivated-customer check on lines 98–131 never executes. The entire customer validation arm of the plan confirmation saga is silently inoperative. A plan referencing deactivated customers will be confirmed and never rolled back via this path.

### W2 — expense_service publishes Kafka events outside any transaction; no outbox
**File:** `expense_service/services/expense_service.py`, lines 170–181 (`approve_expense`) and 220–232 (`reject_expense`)

The database commit happens at line 173 (or 224), and `publish_expense_decided()` is called after it. If Kafka is unavailable at that moment, the expense record is persisted as `approved` or `rejected` but no event is ever emitted. There is no retry mechanism and no outbox table in the expense service. This is the exact failure mode the planning service's outbox pattern was designed to prevent, and it is absent here.

### W3 — publish_expense_submitted() is defined but never called
**File:** `expense_service/producers/expense_events.py`, lines 29–64  
**File:** `expense_service/services/expense_service.py`, `create_expense()` and `submit_expense()`

`publish_expense_submitted()` produces to the `expense.submitted` topic. Neither `create_expense()` nor `submit_expense()` in the service layer calls it. The `expense.submitted` topic is dead. If downstream consumers were to subscribe to it in future, they would receive nothing from the existing codebase.

### W4 — expense.decided consumer does nothing
**File:** `expense_service/consumers/expense_decisions.py`, lines 35–58

The handler `_handle_expense_decided()` logs the decision and returns. The module docstring notes this is "the notification hook for future use." The service is consuming its own events and discarding them. This creates a Kafka consumer group that holds an offset on the topic without providing any value.

### W5 — customer_user_service publishes customer.deactivated directly, without an outbox
**File:** `customer_user_service/routers/customers.py`, lines 339–345

`deactivate_customer()` commits the status change, invalidates the cache, then calls `publish_customer_deactivated()`. If Kafka publish fails (line 345), the customer is already marked inactive in the database and the cache is already cleared, but the `planning_service` receives no `customer.deactivated` event and no plan rollback occurs. There is no retry path.

### W6 — manager_id on expense approval is not validated against user data
**File:** `expense_service/services/expense_service.py`, lines 156–159, 207–210

`approve_expense()` and `reject_expense()` check only that `manager_id` is non-null. They do not query `customer_user_service` (or a local cache) to verify the UUID is a real user with the `manager` role. Any caller can pass an arbitrary UUID as `manager_id` and it will be written to `decided_by` and accepted as a valid approval.

### W7 — PATCH /customers/{id} sets assigned_rep_id without role validation
**File:** `customer_user_service/routers/customers.py`, lines 281–306 (`update_customer`) and lines 386–422 (`assign_rep`)

`PATCH /customers/{id}` accepts `assigned_rep_id` in the `CustomerUpdate` body and sets it without any validation. `PATCH /customers/{id}/assign` validates that `rep_id` belongs to a user with `sales_rep` role. Two endpoints do the same conceptual thing with different safety guarantees, creating an inconsistency a caller can exploit.

### W8 — Plan projection update is outside the main transaction
**File:** `planning_service/services/plan_service.py`, line 150 (after line 148 commit)  
**File:** `planning_service/projections/plan_projection.py`, line 97

`confirm_plan()` commits the plan status change and the outbox row at line 148. Then `update_plan_projection()` is called, which opens a new query sequence and calls `db.commit()` again (plan_projection.py line 97). If the projection update fails between these two commits, the write-side is committed but the read-side (`PlanReadModel`) is stale. The same pattern exists in `activate_plan()` (lines 177–179), `complete_plan()` (lines 205–208), and all visit/call mutations. The CQRS read model can silently diverge from the write model on any projection failure.

### W9 — Customer deactivation saga does not update the plan read-model
**File:** `planning_service/consumers/customer_events.py`, lines 114–130

`_handle_customer_deactivated()` sets `plan.status = DayPlanStatus.draft` for all affected plans and commits. It never calls `update_plan_projection()`. The `PlanReadModel` rows for those plans continue to show `status = "confirmed"` or `status = "active"` after the rollback, so the read-side CQRS endpoints return stale data.

### W10 — N+1 query in plan.confirmed consumer
**File:** `customer_user_service/consumers/plan_confirmed.py`, lines 98–130

`_handle_plan_confirmed()` iterates over `customer_ids` with a separate `SELECT` per customer inside the loop. For a plan with many customers this is N+1 queries to the database. A single `SELECT ... WHERE id IN (...)` would be equivalent and constant-cost.

### W11 — Synchronous HTTP call in service layer with no timeout
**File:** `planning_service/services/plan_service.py`, lines 57–60

```python
async with httpx.AsyncClient() as http:
    rep_resp = await http.get(
        f"http://customer_user_service:8000/users/{payload.rep_id}"
    )
```

No `timeout` argument is set on `httpx.AsyncClient`. A slow or hung `customer_user_service` will hold the planning service request open indefinitely, exhausting the asyncio event loop's capacity. This also creates a tight runtime dependency: `planning_service` cannot create plans if `customer_user_service` is unavailable, even transiently.

### W12 — No authentication at any layer
The Nginx gateway passes all requests through without any credential check. The backend services have no JWT validation, no session management, and no API key verification. Role enforcement relies entirely on the `X-User-Id` header, which is a plain UUID string any caller can forge. This is documented in §4 but is noted here as a structural weakness: the authorisation model assumes trusted callers, which is architecturally inconsistent with the role-based access control rules enforced inside the services.

### W13 — Role enforcement code is duplicated
**File:** `customer_user_service/routers/customers.py`, lines 118–159 (`_require_role`)  
**File:** `customer_user_service/routers/users.py`, lines 77–113 (`_require_administrator`)

Both functions implement: read `X-User-Id` header → parse UUID → query DB → check role → raise 403. The logic is identical in structure but the functions are separate, hard-code different role values, and do not share any abstraction. Adding a third protected action would require writing the same pattern a third time.

### W14 — Health checks are liveness-only; no readiness probe
**All services, `main.py`**

`GET /health` returns `{"status": "ok"}` unconditionally. It does not probe the database connection, Kafka connectivity, or Redis availability. A service with a broken DB connection appears healthy to any orchestrator relying on the health endpoint.

### W15 — Logging level is hardcoded to DEBUG
**File:** `shared/logger.py`, line 16

`logger.setLevel(logging.DEBUG)` is set at import time with no environment variable override. In production this would emit internal state on every request (e.g. "Active customers served from cache", "Visit updated: ..."), which is a performance overhead and potential information disclosure risk.

### W16 — datetime.utcnow() is deprecated (Python 3.12)
**File:** `expense_service/services/expense_service.py`, lines 172 and 223  
**File:** `planning_service/projections/plan_projection.py`, line 69

`datetime.utcnow()` is deprecated since Python 3.12 in favour of `datetime.now(UTC)`. The customer deactivated producer at `customer_user_service/producers/customer_deactivated.py` line 42 correctly uses `datetime.now(UTC)`, so the pattern is inconsistent across the codebase.

### W17 — Frontend hardcodes internal Nginx URL; not configurable
**File:** `frontend_service/routers/pages.py`, line 36

```python
_NGINX_BASE = "http://nginx/api"
```

This URL is not read from an environment variable. The frontend cannot be pointed at a different backend gateway (e.g. for local development outside Docker Compose, or for a Kubernetes ingress) without modifying source code.

### W18 — plan.rolled_back has no consumer
**Kafka topic: `plan.rolled_back`**

Both `customer_user_service/consumers/plan_confirmed.py` (line 33) and `planning_service/consumers/customer_events.py` (lines 116–123) can produce events to `plan.rolled_back`. No service subscribes to this topic. Events are published and dropped. If the intent is for the planning service to update its own plan state in response to a rollback triggered externally by `customer_user_service`, the consumer is missing.

### W19 — templates is a module-level mutable global in pages.py
**File:** `frontend_service/routers/pages.py`, line 32  
**File:** `frontend_service/main.py`, line 60

```python
# pages.py
templates: Jinja2Templates | None = None
```

`main.py` sets `pages.templates = Jinja2Templates(...)` after import. If any code path attempts to render a template before `main.py` finishes setup (e.g. in tests or if the import order changes), `templates` is `None` and calling `templates.TemplateResponse(...)` raises `AttributeError`. This is an implicit initialisation dependency with no guard.

### W20 — Kafka consumers use earliest offset with no dead-letter queue
**All consumers**: `plan_confirmed.py` line 163, `customer_events.py` line 151, `expense_decisions.py` line 74

All consumers set `auto_offset_reset="earliest"`. A permanently malformed message (invalid JSON, missing required fields) will be reprocessed every time the consumer restarts and will generate a log error on every pass, but will never be moved to a dead-letter queue or skipped. There is no poison-message handling.
