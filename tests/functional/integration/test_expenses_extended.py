import uuid

import pytest


async def _create_user(client, unique_suffix, role="sales_rep", tag=None):
    _tag = tag or role[:3]
    resp = await client.post("/api/users", json={
        "name": f"User {_tag} {unique_suffix}",
        "email": f"{_tag}_{unique_suffix}@example.com",
        "password": "password123",
        "role": role,
    })
    assert resp.status_code == 201
    return resp.json()


async def _create_customer(client, unique_suffix):
    resp = await client.post("/api/customers", json={
        "name": f"Acme {unique_suffix}",
        "address": f"1 Main St {unique_suffix}",
    })
    assert resp.status_code == 201
    return resp.json()


async def _create_plan(client, rep_id, unique_suffix):
    resp = await client.post("/api/plans", json={
        "rep_id": str(rep_id),
        "date": "2025-06-01",
        "start_location": f"Start {unique_suffix}",
        "end_location": f"End {unique_suffix}",
    })
    assert resp.status_code == 201
    return resp.json()


async def _add_visit(client, plan_id, customer_id, customer_name):
    resp = await client.post(f"/api/plans/{plan_id}/visits", json={
        "plan_id": str(plan_id),
        "customer_id": str(customer_id),
        "customer_name": customer_name,
        "scheduled_order": 1,
    })
    assert resp.status_code == 201
    return resp.json()


async def _confirm_plan(client, plan_id):
    return await client.patch(f"/api/plans/{plan_id}/confirm")


async def _create_expense(client, rep_id, plan_id, unique_suffix):
    resp = await client.post("/api/expenses", json={
        "rep_id": str(rep_id),
        "plan_id": str(plan_id),
        "category": "fuel",
        "amount": 50.0,
        "description": f"Expense {unique_suffix}",
    })
    assert resp.status_code == 201
    return resp.json()


async def _submit_expense(client, expense_id):
    return await client.patch(f"/api/expenses/{expense_id}/submit")


async def _approve_expense(client, expense_id, manager_id):
    return await client.patch(
        f"/api/expenses/{expense_id}/approve",
        json={"manager_id": str(manager_id)},
    )


async def _reject_expense(client, expense_id, manager_id):
    return await client.patch(
        f"/api/expenses/{expense_id}/reject",
        json={"manager_id": str(manager_id)},
    )


# ---------------------------------------------------------------------------
# State machine errors
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_approve_rejected_expense_returns_409(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep", tag="rep")
    manager = await _create_user(client, unique_suffix, role="manager", tag="mgr")
    customer = await _create_customer(client, unique_suffix)
    plan = await _create_plan(client, rep["id"], unique_suffix)
    await _add_visit(client, plan["id"], customer["id"], customer["name"])
    await _confirm_plan(client, plan["id"])
    expense = await _create_expense(client, rep["id"], plan["id"], unique_suffix)
    await _submit_expense(client, expense["id"])
    await _reject_expense(client, expense["id"], manager["id"])
    resp = await _approve_expense(client, expense["id"], manager["id"])
    assert resp.status_code == 409


@pytest.mark.anyio
async def test_approve_submitted_expense_returns_409(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep", tag="rep")
    manager = await _create_user(client, unique_suffix, role="manager", tag="mgr")
    customer = await _create_customer(client, unique_suffix)
    plan = await _create_plan(client, rep["id"], unique_suffix)
    await _add_visit(client, plan["id"], customer["id"], customer["name"])
    await _confirm_plan(client, plan["id"])
    expense = await _create_expense(client, rep["id"], plan["id"], unique_suffix)
    resp = await _approve_expense(client, expense["id"], manager["id"])
    assert resp.status_code == 409


@pytest.mark.anyio
async def test_reject_already_rejected_expense_returns_409(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep", tag="rep")
    manager = await _create_user(client, unique_suffix, role="manager", tag="mgr")
    customer = await _create_customer(client, unique_suffix)
    plan = await _create_plan(client, rep["id"], unique_suffix)
    await _add_visit(client, plan["id"], customer["id"], customer["name"])
    await _confirm_plan(client, plan["id"])
    expense = await _create_expense(client, rep["id"], plan["id"], unique_suffix)
    await _submit_expense(client, expense["id"])
    await _reject_expense(client, expense["id"], manager["id"])
    resp = await _reject_expense(client, expense["id"], manager["id"])
    assert resp.status_code == 409


@pytest.mark.anyio
async def test_resubmit_submitted_expense_returns_409(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep", tag="rep")
    customer = await _create_customer(client, unique_suffix)
    plan = await _create_plan(client, rep["id"], unique_suffix)
    await _add_visit(client, plan["id"], customer["id"], customer["name"])
    await _confirm_plan(client, plan["id"])
    expense = await _create_expense(client, rep["id"], plan["id"], unique_suffix)
    resp = await client.patch(f"/api/expenses/{expense['id']}/resubmit", json={})
    assert resp.status_code == 409


@pytest.mark.anyio
async def test_resubmit_pending_approval_expense_returns_409(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep", tag="rep")
    customer = await _create_customer(client, unique_suffix)
    plan = await _create_plan(client, rep["id"], unique_suffix)
    await _add_visit(client, plan["id"], customer["id"], customer["name"])
    await _confirm_plan(client, plan["id"])
    expense = await _create_expense(client, rep["id"], plan["id"], unique_suffix)
    await _submit_expense(client, expense["id"])
    resp = await client.patch(f"/api/expenses/{expense['id']}/resubmit", json={})
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# GET /api/expenses
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_list_expenses_filtered_by_status(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep", tag="rep")
    manager = await _create_user(client, unique_suffix, role="manager", tag="mgr")
    customer = await _create_customer(client, unique_suffix)
    plan = await _create_plan(client, rep["id"], unique_suffix)
    await _add_visit(client, plan["id"], customer["id"], customer["name"])
    await _confirm_plan(client, plan["id"])
    expense1 = await _create_expense(client, rep["id"], plan["id"], unique_suffix + "a")
    await _create_expense(client, rep["id"], plan["id"], unique_suffix + "b")
    await _submit_expense(client, expense1["id"])
    await _approve_expense(client, expense1["id"], manager["id"])
    resp = await client.get("/api/expenses?expense_status=approved")
    assert resp.status_code == 200
    assert all(e["status"] == "approved" for e in resp.json())


# ---------------------------------------------------------------------------
# GET /api/expenses/read/status/{status}
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_read_status_endpoint_returns_expenses(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep", tag="rep")
    manager = await _create_user(client, unique_suffix, role="manager", tag="mgr")
    customer = await _create_customer(client, unique_suffix)
    plan = await _create_plan(client, rep["id"], unique_suffix)
    await _add_visit(client, plan["id"], customer["id"], customer["name"])
    await _confirm_plan(client, plan["id"])
    expense = await _create_expense(client, rep["id"], plan["id"], unique_suffix)
    await _submit_expense(client, expense["id"])
    await _approve_expense(client, expense["id"], manager["id"])
    resp = await client.get("/api/expenses/read/status/approved")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert any(e["status"] == "approved" for e in data)


@pytest.mark.anyio
async def test_read_status_approved_only_returns_approved(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep", tag="rep")
    manager = await _create_user(client, unique_suffix, role="manager", tag="mgr")
    customer = await _create_customer(client, unique_suffix)
    plan = await _create_plan(client, rep["id"], unique_suffix)
    await _add_visit(client, plan["id"], customer["id"], customer["name"])
    await _confirm_plan(client, plan["id"])
    expense = await _create_expense(client, rep["id"], plan["id"], unique_suffix)
    await _submit_expense(client, expense["id"])
    await _approve_expense(client, expense["id"], manager["id"])
    resp = await client.get("/api/expenses/read/status/approved")
    assert resp.status_code == 200
    assert all(e["status"] == "approved" for e in resp.json())


@pytest.mark.anyio
async def test_read_status_rejected_only_returns_rejected(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep", tag="rep")
    manager = await _create_user(client, unique_suffix, role="manager", tag="mgr")
    customer = await _create_customer(client, unique_suffix)
    plan = await _create_plan(client, rep["id"], unique_suffix)
    await _add_visit(client, plan["id"], customer["id"], customer["name"])
    await _confirm_plan(client, plan["id"])
    expense = await _create_expense(client, rep["id"], plan["id"], unique_suffix)
    await _submit_expense(client, expense["id"])
    await _reject_expense(client, expense["id"], manager["id"])
    resp = await client.get("/api/expenses/read/status/rejected")
    assert resp.status_code == 200
    assert all(e["status"] == "rejected" for e in resp.json())


@pytest.mark.anyio
async def test_read_status_submitted_returns_submitted(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep", tag="rep")
    customer = await _create_customer(client, unique_suffix)
    plan = await _create_plan(client, rep["id"], unique_suffix)
    await _add_visit(client, plan["id"], customer["id"], customer["name"])
    await _confirm_plan(client, plan["id"])
    await _create_expense(client, rep["id"], plan["id"], unique_suffix)
    resp = await client.get("/api/expenses/read/status/submitted")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.anyio
async def test_read_status_pending_approval_returns_pending(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep", tag="rep")
    customer = await _create_customer(client, unique_suffix)
    plan = await _create_plan(client, rep["id"], unique_suffix)
    await _add_visit(client, plan["id"], customer["id"], customer["name"])
    await _confirm_plan(client, plan["id"])
    expense = await _create_expense(client, rep["id"], plan["id"], unique_suffix)
    await _submit_expense(client, expense["id"])
    resp = await client.get("/api/expenses/read/status/pending_approval")
    assert resp.status_code == 200
    data = resp.json()
    assert any(e["status"] == "pending_approval" for e in data)
