"""Edge-case integration tests for the svp_mic services.

Tests verify boundary conditions and error paths that are independent of
any pre-existing data.  No seed fixtures are used; every test is
self-contained and relies only on the ``client`` fixture and random UUIDs.

Test cases:
- test_list_plans_empty_for_unknown_rep -- GET /api/plans?rep_id=<random>
  returns 200 and an empty list.
- test_list_expenses_empty_for_unknown_rep -- GET /api/expenses?rep_id=<random>
  returns 200 and an empty list.
- test_plan_history_empty_for_unknown_rep -- GET /api/plans/read/history
  with an unknown rep_id returns 200 and an empty list.
- test_expense_history_empty_for_unknown_rep -- GET /api/expenses/read/history
  with an unknown rep_id returns 200 and an empty list.
- test_get_plan_not_found -- GET /api/plans/<random> returns 404.
- test_get_expense_not_found -- GET /api/expenses/<random> returns 404.
- test_get_user_not_found -- GET /api/users/<random> returns 404.
- test_get_customer_not_found -- GET /api/customers/<random> returns 404.
- test_create_plan_empty_body -- POST /api/plans with an empty body returns 422.
- test_create_expense_empty_body -- POST /api/expenses with an empty body
  returns 422.
- test_create_user_empty_body -- POST /api/users with an empty body returns 422.
- test_create_customer_empty_body -- POST /api/customers with an empty body
  returns 422.
- test_add_visit_unknown_plan -- POST /api/plans/<random>/visits returns 404.
"""

import uuid


# ---------------------------------------------------------------------------
# Empty-list responses
# ---------------------------------------------------------------------------

async def test_list_plans_empty_for_unknown_rep(client):
    """GET /api/plans filtered by an unknown rep UUID returns 200 and an empty list."""
    resp = await client.get("/api/plans", params={"rep_id": str(uuid.uuid4())})
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_expenses_empty_for_unknown_rep(client):
    """GET /api/expenses filtered by an unknown rep UUID returns 200 and an empty list."""
    resp = await client.get(
        "/api/expenses", params={"rep_id": str(uuid.uuid4())}
    )
    assert resp.status_code == 200
    assert resp.json() == []


async def test_plan_history_empty_for_unknown_rep(client):
    """GET /api/plans/read/history for an unknown rep_id returns 200 and an empty list."""
    resp = await client.get(
        "/api/plans/read/history", params={"rep_id": str(uuid.uuid4())}
    )
    assert resp.status_code == 200
    assert resp.json() == []


async def test_expense_history_empty_for_unknown_rep(client):
    """GET /api/expenses/read/history for an unknown rep_id returns 200 and an empty list."""
    resp = await client.get(
        "/api/expenses/read/history", params={"rep_id": str(uuid.uuid4())}
    )
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# 404 responses
# ---------------------------------------------------------------------------

async def test_get_plan_not_found(client):
    """GET /api/plans/{id} with a random UUID returns 404."""
    resp = await client.get(f"/api/plans/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_get_expense_not_found(client):
    """GET /api/expenses/{id} with a random UUID returns 404."""
    resp = await client.get(f"/api/expenses/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_get_user_not_found(client):
    """GET /api/users/{id} with a random UUID returns 404."""
    resp = await client.get(f"/api/users/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_get_customer_not_found(client):
    """GET /api/customers/{id} with a random UUID returns 404."""
    resp = await client.get(f"/api/customers/{uuid.uuid4()}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 422 responses — empty request bodies
# ---------------------------------------------------------------------------

async def test_create_plan_empty_body(client):
    """POST /api/plans with an empty body returns 422."""
    resp = await client.post("/api/plans", json={})
    assert resp.status_code == 422


async def test_create_expense_empty_body(client):
    """POST /api/expenses with an empty body returns 422."""
    resp = await client.post("/api/expenses", json={})
    assert resp.status_code == 422


async def test_create_user_empty_body(client):
    """POST /api/users with an empty body returns 422."""
    resp = await client.post("/api/users", json={})
    assert resp.status_code == 422


async def test_create_customer_empty_body(client):
    """POST /api/customers with an empty body returns 422."""
    resp = await client.post("/api/customers", json={})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 404 response — adding a visit to a non-existent plan
# ---------------------------------------------------------------------------

async def test_add_visit_unknown_plan(client):
    """POST /api/plans/{id}/visits with a random plan UUID returns 404."""
    plan_id = str(uuid.uuid4())
    resp = await client.post(
        f"/api/plans/{plan_id}/visits",
        json={
            "plan_id": plan_id,
            "customer_id": str(uuid.uuid4()),
            "customer_name": "Ghost Customer",
            "scheduled_order": 1,
        },
    )
    assert resp.status_code == 404
