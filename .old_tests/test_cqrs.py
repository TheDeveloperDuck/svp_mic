"""Integration tests for the CQRS read-model projections.

Tests verify that write-side operations (create, update, state transitions)
are reflected synchronously in the read-model endpoints exposed by each
service.  Projections are updated in the same transaction as the write, so
no polling or delays are required.

Endpoints under test (Planning Service):
- GET /api/plans/read/history        -- full plan history with optional filters.
- GET /api/plans/read/rep/{rep_id}   -- plan summaries filtered by rep.
- GET /api/plans/read/active         -- all plans currently in ``active`` status.

Endpoints under test (Expense Service):
- GET /api/expenses/read/history     -- full expense history with optional filters.
- GET /api/expenses/read/rep/{rep_id} -- expense summaries filtered by rep.

Test cases:
- test_plan_history_after_create -- creating a plan adds a row with status
  ``"draft"``, visit_count 0, and call_count 0 to the history.
- test_plan_history_visit_count -- adding a visit to a plan increments
  visit_count to 1 in the history.
- test_plan_history_after_confirm -- confirming a plan updates its status
  to ``"confirmed"`` in the history.
- test_plan_read_rep -- GET /api/plans/read/rep/{rep_id} returns only plans
  belonging to the requested rep.
- test_plan_read_active -- activating a plan causes it to appear in the
  active-plans read endpoint.
- test_expense_history_after_create -- creating an expense adds a row with
  status ``"submitted"`` to the history.
- test_expense_history_after_approve -- approving an expense updates its
  status to ``"approved"`` and sets a non-null decided_at in the history.
- test_expense_read_rep -- GET /api/expenses/read/rep/{rep_id} returns only
  expenses belonging to the requested rep.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_plan(client, rep_id: str) -> dict:
    """Create a day plan for the given rep and return the response body.

    Arguments:
    client -- active httpx.AsyncClient.
    rep_id -- UUID string of the sales rep.

    Return value:
    dict -- full JSON response body of the created plan.
    """
    resp = await client.post(
        "/api/plans",
        json={
            "rep_id": rep_id,
            "date": "2026-04-15",
            "start_location": "Dublin",
            "end_location": "Cork",
        },
    )
    resp.raise_for_status()
    return resp.json()


async def _add_visit(
    client,
    plan_id: str,
    customer_id: str,
    customer_name: str,
) -> dict:
    """Add a visit to a plan and return the response body.

    Arguments:
    client        -- active httpx.AsyncClient.
    plan_id       -- UUID string of the parent plan.
    customer_id   -- UUID string of the customer.
    customer_name -- display name of the customer.

    Return value:
    dict -- full JSON response body of the created visit.
    """
    resp = await client.post(
        f"/api/plans/{plan_id}/visits",
        json={
            "plan_id": plan_id,
            "customer_id": customer_id,
            "customer_name": customer_name,
            "scheduled_order": 1,
        },
    )
    resp.raise_for_status()
    return resp.json()


async def _confirm_plan(client, plan_id: str) -> dict:
    """Confirm a plan and return the response body.

    Arguments:
    client  -- active httpx.AsyncClient.
    plan_id -- UUID string of the plan to confirm.

    Return value:
    dict -- full JSON response body of the confirmed plan.
    """
    resp = await client.patch(f"/api/plans/{plan_id}/confirm")
    resp.raise_for_status()
    return resp.json()


async def _activate_plan(client, plan_id: str) -> dict:
    """Activate a plan and return the response body.

    Arguments:
    client  -- active httpx.AsyncClient.
    plan_id -- UUID string of the plan to activate.

    Return value:
    dict -- full JSON response body of the activated plan.
    """
    resp = await client.patch(f"/api/plans/{plan_id}/activate")
    resp.raise_for_status()
    return resp.json()


async def _create_expense(client, rep_id: str, plan_id: str) -> dict:
    """Create an expense submission and return the response body.

    Arguments:
    client  -- active httpx.AsyncClient.
    rep_id  -- UUID string of the sales rep.
    plan_id -- UUID string of the associated day plan.

    Return value:
    dict -- full JSON response body of the created expense.
    """
    resp = await client.post(
        "/api/expenses",
        json={
            "rep_id": rep_id,
            "plan_id": plan_id,
            "category": "fuel",
            "amount": "42.00",
            "description": "Motorway fuel",
        },
    )
    resp.raise_for_status()
    return resp.json()


async def _submit_expense(client, expense_id: str) -> dict:
    """Submit an expense for approval and return the response body.

    Arguments:
    client     -- active httpx.AsyncClient.
    expense_id -- UUID string of the expense to submit.

    Return value:
    dict -- full JSON response body of the submitted expense.
    """
    resp = await client.patch(f"/api/expenses/{expense_id}/submit")
    resp.raise_for_status()
    return resp.json()


async def _approve_expense(client, expense_id: str, manager_id: str) -> dict:
    """Approve a pending expense and return the response body.

    Arguments:
    client     -- active httpx.AsyncClient.
    expense_id -- UUID string of the expense to approve.
    manager_id -- UUID string of the approving manager.

    Return value:
    dict -- full JSON response body of the approved expense.
    """
    resp = await client.patch(
        f"/api/expenses/{expense_id}/approve",
        json={"manager_id": manager_id},
    )
    resp.raise_for_status()
    return resp.json()


def _find_by_id(rows: list[dict], resource_id: str) -> dict | None:
    """Return the first row whose ``id`` matches resource_id, or ``None``.

    Arguments:
    rows        -- list of dicts from a read-model response.
    resource_id -- UUID string to search for.

    Return value:
    dict | None -- the matching row, or ``None`` if not found.
    """
    return next((r for r in rows if r["id"] == resource_id), None)


# ---------------------------------------------------------------------------
# Plan read-model: history
# ---------------------------------------------------------------------------

async def test_plan_history_after_create(client, seed_users):
    """Creating a plan adds a row with status ``draft`` and zero counts to the history.

    Verifies that ``status`` is ``"draft"``, ``visit_count`` is 0, and
    ``call_count`` is 0 immediately after plan creation.
    """
    rep_id = seed_users["rep"]["id"]
    plan = await _create_plan(client, rep_id)

    resp = await client.get(
        "/api/plans/read/history", params={"rep_id": rep_id}
    )
    assert resp.status_code == 200
    row = _find_by_id(resp.json(), plan["id"])
    assert row is not None
    assert row["rep_id"] == rep_id
    assert row["status"] == "draft"
    assert row["visit_count"] == 0
    assert row["call_count"] == 0


async def test_plan_history_visit_count(client, seed_users, seed_customer):
    """Adding a visit to a plan increments visit_count to 1 in the history."""
    rep_id = seed_users["rep"]["id"]
    customer_id = seed_customer["id"]
    customer_name = seed_customer["name"]

    plan = await _create_plan(client, rep_id)
    await _add_visit(client, plan["id"], customer_id, customer_name)

    resp = await client.get(
        "/api/plans/read/history", params={"rep_id": rep_id}
    )
    assert resp.status_code == 200
    row = _find_by_id(resp.json(), plan["id"])
    assert row is not None
    assert row["visit_count"] == 1


async def test_plan_history_after_confirm(client, seed_users, seed_customer):
    """Confirming a plan updates its status to ``confirmed`` in the history."""
    rep_id = seed_users["rep"]["id"]
    customer_id = seed_customer["id"]
    customer_name = seed_customer["name"]

    plan = await _create_plan(client, rep_id)
    await _add_visit(client, plan["id"], customer_id, customer_name)
    await _confirm_plan(client, plan["id"])

    resp = await client.get(
        "/api/plans/read/history", params={"rep_id": rep_id}
    )
    assert resp.status_code == 200
    row = _find_by_id(resp.json(), plan["id"])
    assert row is not None
    assert row["status"] == "confirmed"


# ---------------------------------------------------------------------------
# Plan read-model: rep filter
# ---------------------------------------------------------------------------

async def test_plan_read_rep(client, seed_users):
    """GET /api/plans/read/rep/{rep_id} returns only plans for that rep.

    Creates a plan for the seeded rep and asserts that every row in the
    response belongs to the same rep_id.
    """
    rep_id = seed_users["rep"]["id"]
    await _create_plan(client, rep_id)

    resp = await client.get(f"/api/plans/read/rep/{rep_id}")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) >= 1
    assert all(r["rep_id"] == rep_id for r in rows)


# ---------------------------------------------------------------------------
# Plan read-model: active filter
# ---------------------------------------------------------------------------

async def test_plan_read_active(client, seed_users, seed_customer):
    """Activating a plan causes it to appear in GET /api/plans/read/active.

    Creates a plan, adds a visit, confirms it, activates it, then asserts
    the plan is present in the active-plans read endpoint with status
    ``"active"``.
    """
    rep_id = seed_users["rep"]["id"]
    customer_id = seed_customer["id"]
    customer_name = seed_customer["name"]

    plan = await _create_plan(client, rep_id)
    await _add_visit(client, plan["id"], customer_id, customer_name)
    await _confirm_plan(client, plan["id"])
    await _activate_plan(client, plan["id"])

    resp = await client.get("/api/plans/read/active")
    assert resp.status_code == 200
    rows = resp.json()
    row = _find_by_id(rows, plan["id"])
    assert row is not None
    assert row["status"] == "active"


# ---------------------------------------------------------------------------
# Expense read-model: history
# ---------------------------------------------------------------------------

async def test_expense_history_after_create(client, seed_users):
    """Creating an expense adds a row with status ``submitted`` to the history."""
    rep_id = seed_users["rep"]["id"]
    plan = await _create_plan(client, rep_id)
    expense = await _create_expense(client, rep_id, plan["id"])

    resp = await client.get(
        "/api/expenses/read/history", params={"rep_id": rep_id}
    )
    assert resp.status_code == 200
    row = _find_by_id(resp.json(), expense["id"])
    assert row is not None
    assert row["status"] == "submitted"


async def test_expense_history_after_approve(client, seed_users):
    """Approving an expense updates status to ``approved`` and sets decided_at.

    Creates an expense, submits it, approves it, then asserts that the
    history row reflects ``"approved"`` status and a non-null ``decided_at``.
    """
    rep_id = seed_users["rep"]["id"]
    manager_id = seed_users["manager"]["id"]
    plan = await _create_plan(client, rep_id)
    expense = await _create_expense(client, rep_id, plan["id"])
    await _submit_expense(client, expense["id"])
    await _approve_expense(client, expense["id"], manager_id)

    resp = await client.get(
        "/api/expenses/read/history", params={"rep_id": rep_id}
    )
    assert resp.status_code == 200
    row = _find_by_id(resp.json(), expense["id"])
    assert row is not None
    assert row["status"] == "approved"
    assert row["decided_at"] is not None


# ---------------------------------------------------------------------------
# Expense read-model: rep filter
# ---------------------------------------------------------------------------

async def test_expense_read_rep(client, seed_users):
    """GET /api/expenses/read/rep/{rep_id} returns only expenses for that rep.

    Creates an expense for the seeded rep and asserts that every row in the
    response belongs to the same rep_id.
    """
    rep_id = seed_users["rep"]["id"]
    plan = await _create_plan(client, rep_id)
    await _create_expense(client, rep_id, plan["id"])

    resp = await client.get(f"/api/expenses/read/rep/{rep_id}")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) >= 1
    assert all(r["rep_id"] == rep_id for r in rows)
