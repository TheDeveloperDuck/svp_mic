# SVP Microservices Platform

A Kubernetes-native sales visit planning system composed of four FastAPI microservices deployed to a KinD cluster with Istio service mesh, Kafka event streaming, and a full multi-tier test suite.

---

## Overview

The platform manages the full lifecycle of sales rep day plans and expense submissions. A sales rep creates a day plan, adds customer visits and calls, confirms the plan (triggering a Saga that validates customer status via Kafka), then activates and works through the plan. Expense submissions are created against plans and go through a create → submit → approve/reject → resubmit cycle managed entirely within the expense service.

All inter-service communication goes through Kafka. There is no synchronous service-to-service HTTP. External traffic enters through the Istio ingress gateway, which routes to services by URL prefix.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Client                                                             │
│   └─► Istio IngressGateway :80 (port-forwarded to localhost:8080)  │
│         ├─► /api/users, /api/customers  → customer-user-service     │
│         ├─► /api/plans                  → planning-service          │
│         ├─► /api/expenses               → expense-service           │
│         └─► /                           → frontend-service          │
└─────────────────────────────────────────────────────────────────────┘

Kafka topics (5 total):
  customer.deactivated  ← customer-user-service  →  planning-service
  plan.confirmed        ← planning-service        →  customer-user-service
  plan.rolled_back      ← planning-service        (produced only)
  expense.submitted     ← expense-service         (produced only)
  expense.decided       ← expense-service         →  expense-service
```

**Cluster layout**

| Node | Role |
|---|---|
| svp-control-plane | Kubernetes control-plane |
| svp-worker | Worker |
| svp-worker2 | Worker |

CNI: Calico (for NetworkPolicy enforcement). Service mesh: Istio demo profile with STRICT mTLS.

**Data stores (StatefulSets, namespace `svp`)**

| StatefulSet | Purpose |
|---|---|
| svp-customer-user-db | PostgreSQL for customer-user-service |
| svp-planning-db | PostgreSQL for planning-service |
| svp-expense-db | PostgreSQL for expense-service |
| svp-kafka | Kafka broker |
| svp-zookeeper | Zookeeper (Kafka coordination) |
| svp-redis | Redis (customer-user-service cache only) |

---

## Services

### customer-user-service

Manages users (sales reps, managers, administrators) and customers. Exposes a Redis-cached list of active customers. Publishes `customer.deactivated` events and consumes `plan.confirmed` events.

**Kubernetes service port:** 8001 → container 8000

**Database tables:** `users`, `customers`, `customer_priority_flags`, `manager_reps`

**User roles:** `sales_rep`, `manager`, `administrator`

**Customer status lifecycle:** active (default) → deactivated (soft-delete via `PATCH /{id}/deactivate`)

**Redis cache:** The key `active_customers` holds a JSON-serialised list of `CustomerResponse` dicts. It is invalidated on every write (create, update, deactivate, flag, assign) and repopulated on cache miss. Redis failures are swallowed so they do not break write operations.

**Kafka produced:** `customer.deactivated` (on `PATCH /customers/{id}/deactivate`)

**Kafka consumed:** `plan.confirmed` — validates all customer IDs in the plan are still active; publishes `plan.rolled_back` if any are deactivated.

---

### planning-service

Manages day plans and their child visits and calls. Implements the Transactional Outbox pattern for all Kafka publishing and a Saga for plan confirmation. Maintains a `plan_read_model` CQRS projection.

**Kubernetes service port:** 8002 → container 8000

**Database tables:** `day_plans`, `visits`, `calls`, `outbox`, `plan_read_model`

**Plan status lifecycle:** `draft` → `confirmed` → `active` → `completed`

**Visit status lifecycle:** `scheduled` → `completed` / `skipped`

**Call status lifecycle:** `scheduled` → `completed` / `skipped`

**Transactional Outbox:** All Kafka events are written to the `outbox` table inside the same database transaction as the state change. A background poller runs every 5 seconds, publishes pending rows to Kafka, and marks them `published`.

**Saga — plan confirmation:**
1. `PATCH /plans/{id}/confirm` transitions plan to `confirmed` and writes a `plan.confirmed` outbox row atomically.
2. Outbox poller publishes to `plan.confirmed` topic.
3. customer-user-service validates customers; if any are deactivated it publishes `plan.rolled_back`.
4. planning-service `customer_events` consumer receives `plan.rolled_back` and calls the saga rollback handler, which writes a `plan.rolled_back` outbox row and resets the plan to `draft`.

**Kafka consumed:** `customer.deactivated` (rolls back all `confirmed` or `active` plans for that customer) and `plan.rolled_back` (saga rollback handler)

**Kafka produced (via outbox):** `plan.confirmed`, `plan.rolled_back`

---

### expense-service

Manages expense submissions linked to day plans. Implements a CQRS `expense_read_model` projection.

**Kubernetes service port:** 8003 → container 8000

**Database tables:** `expense_submissions`, `expense_read_model`

**Expense status lifecycle:** `submitted` → `pending_approval` → `approved` / `rejected` → (if rejected) `submitted` (via resubmit)

**Expense categories:** `fuel`, `food`, `overnight_stay`, `tolls`

**Kafka produced:** `expense.submitted` (on `PATCH /{id}/submit`), `expense.decided` (on approve or reject)

**Kafka consumed:** `expense.decided` — notification hook only; logs the outcome, no database action.

---

### frontend-service

Serves a web UI. All traffic not matched by `/api/` prefixes routes here.

**Kubernetes service port:** 8000 → container 8000

---

## Kafka Topics

| Topic | Producer | Consumer | Purpose |
|---|---|---|---|
| `customer.deactivated` | customer-user-service | planning-service | Triggers rollback of all confirmed/active plans for the deactivated customer |
| `plan.confirmed` | planning-service (outbox) | customer-user-service | customer-user-service validates customer active status; publishes `plan.rolled_back` if not |
| `plan.rolled_back` | planning-service (outbox) | — | Informational; records saga rollback outcome |
| `expense.submitted` | expense-service | — | Informational; records submission transition |
| `expense.decided` | expense-service | expense-service | Notification hook; consumer logs outcome only |

All consumers use an indefinite `while True` retry loop. The `AIOKafkaConsumer` is instantiated fresh on each iteration. `asyncio.CancelledError` triggers clean shutdown (`consumer.stop()` then `return`). Any other exception triggers a 5-second sleep and reconnect. This ensures consumers survive Kafka restarts without the pod needing to restart.

---

## Shared Module

Located at `shared/`. Imported by all four services.

**`shared/logger.py`** — structured logger instance used across all services.

**`shared/tracing.py`** — OpenTelemetry tracing setup. Configures a `BatchSpanExporter` pointing at Jaeger. Included in each service's startup.

**`shared/exceptions.py`** — domain exceptions:
- `CustomerDeactivatedError` — raised when operating on a deactivated customer.
- `PlanConfirmationError` — raised when a plan cannot be confirmed (e.g. no visits or calls).
- `VisitCompletionError` — raised when a visit completion is invalid.
- `ExpenseApprovalError` — raised when an expense cannot be approved or rejected.
- `OutboxPublishError` — raised when Kafka publishing fails in a producer.

---

## Infrastructure

### KinD cluster

Defined in `kind-config.yaml`. Three nodes: one control-plane, two workers. Each node mounts `/sys/fs/bpf` and exposes `hostPort` 80 on the control-plane for the Istio ingress gateway.

### Istio

Installed with the `demo` profile. STRICT mTLS is enforced globally via a `PeerAuthentication` resource in the `svp` namespace. All app pods annotate `traffic.sidecar.istio.io/excludeOutboundPorts: "5432,6379,9092,2181"` so database, Redis, and Kafka traffic bypasses Envoy.

**Routing (VirtualService + Gateway):**

All traffic enters through `istio-ingressgateway` on port 80. A single `Gateway` resource selects hosts `*`. Four `VirtualService` resources route by URI prefix:

| Prefix | Service |
|---|---|
| `/api/users`, `/api/customers` | customer-user-service:8001 |
| `/api/plans` | planning-service:8002 |
| `/api/expenses` | expense-service:8003 |
| `/` (catch-all) | frontend-service:8000 |

**DestinationRules:** Each service has a `DestinationRule` requiring TLS mode `ISTIO_MUTUAL`.

**Telemetry:** A `Telemetry` resource in the `svp` namespace enables 100% trace sampling (overrides the demo profile default of 1%).

**AuthorizationPolicy:** A default deny-all policy in `svp` is overridden by per-service `ALLOW` policies that permit traffic from `istio-ingressgateway` and from other svp services.

**EnvoyFilter (rate limiting):** Applied to customer-user-service pods. Local rate limiter: 10 tokens per fill, 1-second fill interval, 100% enabled and enforced. Responses that exceed the limit return HTTP 429 with header `x-local-rate-limit: true`.

### Network Policies

Calico `NetworkPolicy` resources in the `svp` namespace enforce isolation at the pod level independently of Istio. Each service database only accepts traffic from its own service pod. Kafka accepts traffic from all four app services. Redis accepts traffic from customer-user-service only. Ingress from the `istio-system` namespace is allowed for each app service. All egress is allowed by default.

### Observability

Installed from `istio-1.21.0/samples/addons/`:

| Tool | Purpose |
|---|---|
| Prometheus | Metrics scraping (Istio + application) |
| Jaeger | Distributed tracing |
| Kiali | Service mesh visualisation |
| Grafana | Dashboard |

Prometheus: port 9090. Jaeger (tracing): port 16686.

---

## Deployment

### Prerequisites

- `docker`
- `kind`
- `kubectl`
- `helm`
- `istioctl` (1.21.x)
- Python 3.12 with `pip`

### First-time setup

```bash
# 1. Create cluster, install Calico, build images, load images, deploy Helm chart
python plat_scripts/deploy.py

# 2. Install Istio
python plat_scripts/install_istio.py

# 3. Install observability stack
python plat_scripts/install_observability.py
```

`deploy.py` runs six steps in sequence:

1. Create the KinD cluster from `kind-config.yaml`
2. Apply Calico CNI manifests and wait for node readiness
3. Build Docker images for all four services (build context: project root)
4. Load images into KinD
5. `helm install` (or `helm upgrade`) the `svp` chart from `helm/svp/`
6. Wait for all deployments to reach ready state

`install_istio.py` runs nine steps:

1. Verify `istioctl` is available
2. Install Istio with demo profile
3. Verify `istiod` is running
4. Label the `svp` namespace with `istio-injection=enabled`
5. Restart all deployments to inject sidecars
6. Wait for all pods to show 2/2 READY
7. Apply security policies (PeerAuthentication, AuthorizationPolicy)
8. Apply networking resources (Gateway, VirtualService, DestinationRule, EnvoyFilter)
9. Apply Telemetry resource

### Port forwarding

After cluster is ready, forward the ingress gateway to localhost:

```bash
kubectl port-forward -n istio-system svc/istio-ingressgateway 8080:80
```

All API calls go through `http://localhost:8080`.

### Redeployment

After changing service code:

```bash
# Rebuild and reload a single service (e.g. planning-service)
docker build -t svp-planning-service:latest -f planning_service/Dockerfile .
kind load docker-image svp-planning-service:latest --name svp
kubectl rollout restart deployment/svp-planning-service -n svp
kubectl rollout status deployment/svp-planning-service -n svp --timeout=120s
```

Use `-f <service>/Dockerfile .` from the project root — the Dockerfiles copy both the service directory and `shared/`, which only exist relative to the root.

### Upgrading the Helm chart

```bash
helm upgrade svp helm/svp/ -n svp
```

---

## API Reference

All paths are relative to `http://localhost:8080`. All request and response bodies are JSON. Timestamps are ISO 8601 UTC.

### customer-user-service — Users (`/api/users`)

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/users` | — | List all users |
| `GET` | `/api/users/{user_id}` | — | Get user by ID |
| `POST` | `/api/users` | — | Create user (201) |
| `PATCH` | `/api/users/{user_id}` | — | Update user fields |
| `DELETE` | `/api/users/{user_id}` | `X-User-Id` (administrator) | Hard-delete user (204) |

**`POST /api/users` body**

```json
{
  "name": "string",
  "email": "string (email)",
  "password": "string",
  "role": "sales_rep | manager | administrator"
}
```

**`UserResponse`**

```json
{
  "id": "uuid",
  "name": "string",
  "email": "string",
  "role": "sales_rep | manager | administrator",
  "is_active": true,
  "created_at": "datetime"
}
```

### customer-user-service — Customers (`/api/customers`)

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/customers` | — | List active customers (Redis-cached) |
| `GET` | `/api/customers/{customer_id}` | — | Get customer by ID |
| `POST` | `/api/customers` | — | Create customer (201) |
| `PATCH` | `/api/customers/{customer_id}` | — | Update customer fields |
| `PATCH` | `/api/customers/{customer_id}/deactivate` | — | Soft-delete customer; fires `customer.deactivated` (409 if already deactivated) |
| `PATCH` | `/api/customers/{customer_id}/flag` | `X-User-Id` (manager) | Mark customer as priority |
| `PATCH` | `/api/customers/{customer_id}/assign` | — | Assign a sales rep |

**`POST /api/customers` body**

```json
{
  "name": "string",
  "address": "string",
  "lat": null,
  "lng": null,
  "is_priority": false,
  "assigned_rep_id": null
}
```

**`CustomerResponse`**

```json
{
  "id": "uuid",
  "name": "string",
  "address": "string",
  "lat": null,
  "lng": null,
  "is_active": true,
  "is_priority": false,
  "assigned_rep_id": null,
  "created_at": "datetime"
}
```

**`PATCH /api/customers/{id}/assign` body:** `{ "rep_id": "uuid" }` — target user must exist and hold `sales_rep` role.

### planning-service — Plans (`/api/plans`)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/plans` | Create plan in `draft` state (201) |
| `GET` | `/api/plans` | List plans; optional `?rep_id=uuid` |
| `GET` | `/api/plans/{plan_id}` | Get plan by ID |
| `PATCH` | `/api/plans/{plan_id}/confirm` | Transition `draft` → `confirmed`; requires at least one visit or call (422 if empty, 409 if wrong state) |
| `PATCH` | `/api/plans/{plan_id}/activate` | Transition `confirmed` → `active` (409 if wrong state) |
| `PATCH` | `/api/plans/{plan_id}/complete` | Transition `active` → `completed` (409 if wrong state) |
| `POST` | `/api/plans/{plan_id}/visits` | Add a visit to a draft plan (409 if not draft) (201) |
| `POST` | `/api/plans/{plan_id}/calls` | Add a call to a draft plan (201) |
| `PATCH` | `/api/plans/{plan_id}/visits/{visit_id}` | Update visit status or outcome notes |
| `PATCH` | `/api/plans/{plan_id}/calls/{call_id}` | Update call status or outcome notes |

**`POST /api/plans` body**

```json
{
  "rep_id": "uuid",
  "date": "YYYY-MM-DD",
  "start_location": "string",
  "end_location": "string"
}
```

**`DayPlanResponse`**

```json
{
  "id": "uuid",
  "rep_id": "uuid",
  "status": "draft | confirmed | active | completed",
  "start_location": "string",
  "end_location": "string",
  "map_url": null,
  "date": "YYYY-MM-DD",
  "created_at": "datetime"
}
```

**`POST /api/plans/{id}/visits` body**

```json
{
  "plan_id": "uuid",
  "customer_id": "uuid",
  "customer_name": "string",
  "scheduled_order": 1
}
```

**`VisitResponse`**

```json
{
  "id": "uuid",
  "plan_id": "uuid",
  "customer_id": "uuid",
  "customer_name": "string",
  "status": "scheduled | completed | skipped",
  "outcome_notes": null,
  "scheduled_order": 1,
  "created_at": "datetime"
}
```

**`POST /api/plans/{id}/calls` body**

```json
{
  "plan_id": "uuid",
  "customer_id": "uuid",
  "customer_name": "string",
  "duration_minutes": 30
}
```

**`CallResponse`**

```json
{
  "id": "uuid",
  "plan_id": "uuid",
  "customer_id": "uuid",
  "customer_name": "string",
  "status": "scheduled | completed | skipped",
  "outcome_notes": null,
  "duration_minutes": 30,
  "created_at": "datetime"
}
```

### planning-service — Read model (`/api/plans/read`)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/plans/read/rep/{rep_id}` | All plan summaries for a rep |
| `GET` | `/api/plans/read/active` | All plans in `active` status |
| `GET` | `/api/plans/read/history` | Full history; optional `?rep_id=uuid&date=YYYY-MM-DD` |

**`PlanReadModelResponse`**

```json
{
  "id": "uuid",
  "rep_id": "uuid",
  "status": "string",
  "date": "YYYY-MM-DD",
  "visit_count": 0,
  "call_count": 0,
  "updated_at": "datetime"
}
```

### expense-service — Expenses (`/api/expenses`)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/expenses` | Create expense in `submitted` state (201) |
| `GET` | `/api/expenses` | List expenses; optional `?rep_id=uuid&expense_status=string` |
| `GET` | `/api/expenses/{expense_id}` | Get expense by ID |
| `PATCH` | `/api/expenses/{expense_id}/submit` | Transition `submitted` → `pending_approval`; fires `expense.submitted` |
| `PATCH` | `/api/expenses/{expense_id}/approve` | Transition `pending_approval` → `approved`; fires `expense.decided` |
| `PATCH` | `/api/expenses/{expense_id}/reject` | Transition `pending_approval` → `rejected`; fires `expense.decided` |
| `PATCH` | `/api/expenses/{expense_id}/resubmit` | Transition `rejected` → `submitted`; amends fields |

**`POST /api/expenses` body**

```json
{
  "rep_id": "uuid",
  "plan_id": "uuid",
  "category": "fuel | food | overnight_stay | tolls",
  "amount": "decimal",
  "description": null,
  "receipt_image": null
}
```

**`ExpenseSubmissionResponse`**

```json
{
  "id": "uuid",
  "rep_id": "uuid",
  "plan_id": "uuid",
  "category": "fuel | food | overnight_stay | tolls",
  "amount": "decimal",
  "description": null,
  "receipt_image": null,
  "status": "submitted | pending_approval | approved | rejected",
  "submitted_at": "datetime",
  "decided_at": null,
  "decided_by": null
}
```

**`PATCH /{id}/approve` and `PATCH /{id}/reject` body:** `{ "manager_id": "uuid" }`

**`PATCH /{id}/resubmit` body (all fields optional):**

```json
{
  "amount": null,
  "description": null,
  "receipt_image": null
}
```

### expense-service — Read model (`/api/expenses/read`)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/expenses/read/rep/{rep_id}` | Expense summaries for a rep |
| `GET` | `/api/expenses/read/status/{status}` | Expenses filtered by status string |
| `GET` | `/api/expenses/read/history` | Full history; optional `?rep_id=uuid&status=string` |

**`ExpenseReadModelResponse`**

```json
{
  "id": "uuid",
  "rep_id": "uuid",
  "plan_id": "uuid",
  "category": "string",
  "amount": "decimal",
  "status": "string",
  "submitted_at": "datetime",
  "decided_at": null,
  "updated_at": "datetime"
}
```

---

## Test Suite

### Structure

```
tests/
├── functional/
│   ├── conftest.py          # function-scoped client and unique_suffix fixtures
│   ├── e2e/
│   │   ├── test_full_lifecycle.py       # 11 tests
│   │   └── test_scale_data_volume.py    # 14 tests
│   ├── integration/
│   │   ├── test_authorization.py
│   │   ├── test_customer_deactivation_kafka.py
│   │   ├── test_customer_deactivation_plan_rollback.py
│   │   ├── test_expense_read_model.py
│   │   ├── test_expense_resubmission.py
│   │   ├── test_expense_workflow.py
│   │   ├── test_migrations.py
│   │   ├── test_network_policy.py
│   │   ├── test_observability.py
│   │   ├── test_plan_confirmed_kafka.py
│   │   ├── test_plan_lifecycle.py
│   │   ├── test_plan_read_model.py
│   │   ├── test_rbac.py
│   │   ├── test_redis_cache.py
│   │   └── test_routing.py              # 144 tests total across all integration files
│   ├── regression/
│   │   └── test_existing_suite_on_k8s.py  # 75 tests
│   └── unit/
│       ├── test_helm_templates.py         # 11 tests
│       ├── test_istio_manifest_yaml.py    # 54 tests
│       ├── test_network_policy_yaml.py    # 55 tests
│       └── test_tracing_unit.py           # 15 tests
└── stress/
    ├── conftest.py          # session-scoped port-forward setup + cluster teardown
    ├── concurrent/
    │   ├── test_burst_patterns.py         # 4 tests
    │   ├── test_flat_concurrency.py       # 57 parametrized tests
    │   └── test_operation_concurrency.py  # 9 tests
    └── resilience/
        ├── test_fault_injection.py        # 6 tests
        ├── test_pod_failure.py            # 6 tests
        └── test_rate_limiting.py          # 7 tests
```

**Total: 468 tests** — 379 functional, 89 stress.

### Configuration

`pytest.ini`:

```ini
[pytest]
asyncio_mode = auto
asyncio_default_fixture_loop_scope = function
testpaths = tests
log_file_level = DEBUG
log_format = %(asctime)s %(levelname)-8s %(name)s %(message)s
```

Log output goes to `test_logs/` (timestamped file per run, created by the stress conftest).

### Running the functional suite

```bash
# All 379 functional tests
pytest tests/functional/ -v

# Specific subdirectory
pytest tests/functional/e2e/ -v
pytest tests/functional/integration/ -v
pytest tests/functional/regression/ -v
pytest tests/functional/unit/ -v
```

The functional suite requires the cluster to be up and `kubectl port-forward` running on localhost:8080. There is no session-level setup in the functional conftest — start the port-forward manually before running.

### Running the stress suite

```bash
# All 89 stress tests
pytest tests/stress/ -v

# Specific subdirectory
pytest tests/stress/concurrent/ -v
pytest tests/stress/resilience/ -v
```

The stress conftest `stress_session_teardown` fixture (session-scoped, autouse):

- **Setup (before yield):** calls `start_port_forwards()` which kills any existing port-forwards on 8080/9090/16686 and starts new ones for the ingress gateway, Prometheus, and Jaeger.
- **Teardown (after yield):** restarts all deployments in the `svp` namespace, waits for `svp-planning-service` rollout with a 120-second timeout, sleeps 90 seconds, then restarts port-forwards.

### Session management and known constraints

- The functional suite has no session-level setup. Ensure `kubectl port-forward` on 8080, 9090, and 16686 is running before starting.

```bash
kubectl port-forward -n istio-system svc/istio-ingressgateway 8080:80 &
kubectl port-forward -n istio-system svc/prometheus 9090:9090 &
kubectl port-forward -n istio-system svc/tracing 16686:80 &
```

- The stress suite manages its own port-forwards. Do not run the functional and stress suites simultaneously.
- Fault injection tests (`test_fault_injection.py`) apply Istio `VirtualService` fault injection manifests from `tests/stress/resilience/manifests/` before each test and remove them in teardown. Running these against the functional suite endpoints will cause failures.
- Pod failure tests (`test_pod_failure.py`) delete pods directly. The teardown restarts all deployments and waits for readiness.
- Rate limiting tests (`test_rate_limiting.py`) apply a rate-limit `EnvoyFilter` from the manifests directory and remove it in teardown.
- After the stress suite completes, the cluster teardown restarts all deployments and restores port-forwards, leaving the cluster in a clean state.
- The `stress` pytest marker is registered in both conftest files.

---

## Design Decisions

**Transactional Outbox over direct Kafka publishing** — The planning-service writes Kafka events to an `outbox` table inside the same database transaction as the plan state change. This eliminates the dual-write problem: if the application crashes after writing state but before publishing, the poller will publish on the next tick. The poller runs every 5 seconds.

**CQRS read models** — `plan_read_model` (planning-service) and `expense_read_model` (expense-service) are separate tables updated by projection handlers after every write-side state change. This allows the read paths to return pre-aggregated data (visit/call counts, status) without joining across multiple tables on every request.

**Indefinite consumer retry loops** — All Kafka consumers instantiate `AIOKafkaConsumer` inside a `while True` loop. If Kafka is unavailable at startup, the consumer catches the exception, logs a warning, sleeps 5 seconds, and retries. This ensures a pod that starts before Kafka is ready will eventually connect without needing a pod restart. The pod health endpoint (`/health`) is HTTP-only and will report healthy even if the consumer task is in its retry delay, which is intentional — the pod is healthy, the consumer is self-recovering.

**`sidecar.istio.io/excludeOutboundPorts`** — Kafka, PostgreSQL, Redis, and Zookeeper traffic bypasses Envoy. These are intra-cluster connections that do not need mTLS enforcement and would otherwise require `ServiceEntry` resources for each external host. Excluding the ports keeps the mesh configuration simple.

**No synchronous inter-service HTTP** — All cross-service coordination happens through Kafka. This allows each service to operate independently and means a service outage does not cascade synchronously to its callers. The trade-off is eventual consistency: a plan rollback from `plan.rolled_back` may take several seconds to propagate depending on the outbox poller interval and consumer lag.

**Redis cache for active customers only** — The customer list is the highest-read, lowest-write data in the system. Caching it under a single key (`active_customers`) with full invalidation on any write is simple and correct. No per-customer cache keys, no cache stampede concerns at this scale. Redis failures are caught and logged without breaking the endpoint.

**Calico NetworkPolicy + Istio AuthorizationPolicy** — Both layers enforce access control. Calico operates at L3/L4 (pod CIDR, port) independently of Istio; Istio operates at L7 (service identity, mTLS). Having both means a misconfigured Istio policy does not bypass network isolation, and a misconfigured NetworkPolicy does not bypass the mesh's identity-based access control.
