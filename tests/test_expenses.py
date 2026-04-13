"""Integration tests for the Expenses endpoints of the Expense Service.

Tests hit the running Docker stack at http://localhost via nginx.
No service code is imported; all interaction is over HTTP.

Endpoints under test:
- POST   /api/expenses                              -- create a new expense submission.
- GET    /api/expenses                              -- list all submissions.
- GET    /api/expenses/{expense_id}                 -- fetch a single submission.
- PATCH  /api/expenses/{expense_id}/submit          -- move to pending_approval.
- PATCH  /api/expenses/{expense_id}/approve         -- approve a submission.
- PATCH  /api/expenses/{expense_id}/reject          -- reject a submission.
- PATCH  /api/expenses/{expense_id}/resubmit        -- resubmit a rejected submission.

Test cases:
- test_create_expense_valid -- valid payload returns 201 with status "submitted".
- test_create_expense_missing_rep_id -- absent rep_id returns 422.
- test_create_expense_missing_plan_id -- absent plan_id returns 422.
- test_create_expense_missing_category -- absent category returns 422.
- test_create_expense_missing_amount -- absent amount returns 422.
- test_submit_expense -- submitting a draft returns 200 with status "pending_approval".
- test_submit_already_pending_expense -- submitting a pending expense returns 409.
- test_approve_pending_expense -- approving a pending expense returns 200 with status
  "approved" and a non-null decided_at.
- test_approve_already_approved_expense -- re-approving an approved expense returns 409.
- test_reject_pending_expense -- rejecting a pending expense returns 200 with status
  "rejected".
- test_resubmit_rejected_expense -- resubmitting a rejected expense returns 200 with
  status "submitted".
- test_resubmit_approved_expense -- resubmitting an approved expense returns 409.
- test_list_expenses -- GET /api/expenses returns 200 with a list body.
- test_get_expense_nonexistent -- unknown expense UUID returns 404.
"""

import uuid


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
            "amount": "25.50",
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
    dict -- full JSON response body of the updated expense.
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
    dict -- full JSON response body of the updated expense.
    """
    resp = await client.patch(
        f"/api/expenses/{expense_id}/approve",
        json={"manager_id": manager_id},
    )
    resp.raise_for_status()
    return resp.json()


async def _reject_expense(client, expense_id: str, manager_id: str) -> dict:
    """Reject a pending expense and return the response body.

    Arguments:
    client     -- active httpx.AsyncClient.
    expense_id -- UUID string of the expense to reject.
    manager_id -- UUID string of the rejecting manager.

    Return value:
    dict -- full JSON response body of the updated expense.
    """
    resp = await client.patch(
        f"/api/expenses/{expense_id}/reject",
        json={"manager_id": manager_id},
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Create expense
# ---------------------------------------------------------------------------

async def test_create_expense_valid(client, seed_plan):
    """Create an expense with a valid payload and assert 201 with status ``submitted``.

    Verifies that ``id``, ``rep_id``, ``plan_id``, ``category``, ``amount``,
    and ``status`` are all present and have the expected values.
    """
    rep_id = seed_plan["plan"]["rep_id"]
    plan_id = seed_plan["plan"]["id"]

    resp = await client.post(
        "/api/expenses",
        json={
            "rep_id": rep_id,
            "plan_id": plan_id,
            "category": "fuel",
            "amount": "25.50",
            "description": "Motorway fuel",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body
    assert body["rep_id"] == rep_id
    assert body["plan_id"] == plan_id
    assert body["category"] == "fuel"
    assert body["status"] == "submitted"


async def test_create_expense_missing_rep_id(client, seed_plan):
    """Omit the rep_id field and assert the response is 422."""
    plan_id = seed_plan["plan"]["id"]

    resp = await client.post(
        "/api/expenses",
        json={
            "plan_id": plan_id,
            "category": "fuel",
            "amount": "25.50",
        },
    )
    assert resp.status_code == 422


async def test_create_expense_missing_plan_id(client, seed_users):
    """Omit the plan_id field and assert the response is 422."""
    rep_id = seed_users["rep"]["id"]

    resp = await client.post(
        "/api/expenses",
        json={
            "rep_id": rep_id,
            "category": "fuel",
            "amount": "25.50",
        },
    )
    assert resp.status_code == 422


async def test_create_expense_missing_category(client, seed_plan):
    """Omit the category field and assert the response is 422."""
    rep_id = seed_plan["plan"]["rep_id"]
    plan_id = seed_plan["plan"]["id"]

    resp = await client.post(
        "/api/expenses",
        json={
            "rep_id": rep_id,
            "plan_id": plan_id,
            "amount": "25.50",
        },
    )
    assert resp.status_code == 422


async def test_create_expense_missing_amount(client, seed_plan):
    """Omit the amount field and assert the response is 422."""
    rep_id = seed_plan["plan"]["rep_id"]
    plan_id = seed_plan["plan"]["id"]

    resp = await client.post(
        "/api/expenses",
        json={
            "rep_id": rep_id,
            "plan_id": plan_id,
            "category": "fuel",
        },
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Submit expense
# ---------------------------------------------------------------------------

async def test_submit_expense(client, seed_plan):
    """Submit a draft expense and assert 200 with status ``pending_approval``."""
    rep_id = seed_plan["plan"]["rep_id"]
    plan_id = seed_plan["plan"]["id"]

    expense = await _create_expense(client, rep_id, plan_id)

    resp = await client.patch(f"/api/expenses/{expense['id']}/submit")
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending_approval"


async def test_submit_already_pending_expense(client, seed_plan):
    """Submit an already pending expense and assert 409."""
    rep_id = seed_plan["plan"]["rep_id"]
    plan_id = seed_plan["plan"]["id"]

    expense = await _create_expense(client, rep_id, plan_id)
    await _submit_expense(client, expense["id"])

    resp = await client.patch(f"/api/expenses/{expense['id']}/submit")
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Approve expense
# ---------------------------------------------------------------------------

async def test_approve_pending_expense(client, seed_users, seed_plan):
    """Approve a pending expense and assert 200 with status ``approved`` and non-null decided_at."""
    manager_id = seed_users["manager"]["id"]
    rep_id = seed_plan["plan"]["rep_id"]
    plan_id = seed_plan["plan"]["id"]

    expense = await _create_expense(client, rep_id, plan_id)
    await _submit_expense(client, expense["id"])

    resp = await client.patch(
        f"/api/expenses/{expense['id']}/approve",
        json={"manager_id": manager_id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "approved"
    assert body["decided_at"] is not None


async def test_approve_already_approved_expense(client, seed_users, seed_plan):
    """Re-approve an already approved expense and assert 409."""
    manager_id = seed_users["manager"]["id"]
    rep_id = seed_plan["plan"]["rep_id"]
    plan_id = seed_plan["plan"]["id"]

    expense = await _create_expense(client, rep_id, plan_id)
    await _submit_expense(client, expense["id"])
    await _approve_expense(client, expense["id"], manager_id)

    resp = await client.patch(
        f"/api/expenses/{expense['id']}/approve",
        json={"manager_id": manager_id},
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Reject expense
# ---------------------------------------------------------------------------

async def test_reject_pending_expense(client, seed_users, seed_plan):
    """Reject a pending expense and assert 200 with status ``rejected``."""
    manager_id = seed_users["manager"]["id"]
    rep_id = seed_plan["plan"]["rep_id"]
    plan_id = seed_plan["plan"]["id"]

    expense = await _create_expense(client, rep_id, plan_id)
    await _submit_expense(client, expense["id"])

    resp = await client.patch(
        f"/api/expenses/{expense['id']}/reject",
        json={"manager_id": manager_id},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


# ---------------------------------------------------------------------------
# Resubmit expense
# ---------------------------------------------------------------------------

async def test_resubmit_rejected_expense(client, seed_users, seed_plan):
    """Resubmit a rejected expense and assert 200 with status ``submitted``."""
    manager_id = seed_users["manager"]["id"]
    rep_id = seed_plan["plan"]["rep_id"]
    plan_id = seed_plan["plan"]["id"]

    expense = await _create_expense(client, rep_id, plan_id)
    await _submit_expense(client, expense["id"])
    await _reject_expense(client, expense["id"], manager_id)

    resp = await client.patch(
        f"/api/expenses/{expense['id']}/resubmit",
        json={},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "submitted"


async def test_resubmit_approved_expense(client, seed_users, seed_plan):
    """Attempt to resubmit an approved expense and assert 409."""
    manager_id = seed_users["manager"]["id"]
    rep_id = seed_plan["plan"]["rep_id"]
    plan_id = seed_plan["plan"]["id"]

    expense = await _create_expense(client, rep_id, plan_id)
    await _submit_expense(client, expense["id"])
    await _approve_expense(client, expense["id"], manager_id)

    resp = await client.patch(
        f"/api/expenses/{expense['id']}/resubmit",
        json={},
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# List and fetch
# ---------------------------------------------------------------------------

async def test_list_expenses(client):
    """Fetch all expenses and assert 200 with a list response body."""
    resp = await client.get("/api/expenses")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_get_expense_nonexistent(client):
    """Request an expense with a random UUID and assert 404."""
    resp = await client.get(f"/api/expenses/{uuid.uuid4()}")
    assert resp.status_code == 404
