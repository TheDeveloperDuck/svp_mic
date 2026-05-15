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


async def _add_visit(client, plan_id, customer_id, customer_name, order=1):
    resp = await client.post(f"/api/plans/{plan_id}/visits", json={
        "plan_id": str(plan_id),
        "customer_id": str(customer_id),
        "customer_name": customer_name,
        "scheduled_order": order,
    })
    assert resp.status_code == 201
    return resp.json()


async def _confirm_plan(client, plan_id):
    return await client.patch(f"/api/plans/{plan_id}/confirm")


async def _activate_plan(client, plan_id):
    return await client.patch(f"/api/plans/{plan_id}/activate")


async def _complete_plan(client, plan_id):
    return await client.patch(f"/api/plans/{plan_id}/complete")


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
# GET /api/plans/read/history
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_plan_history_reflects_active_status(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep")
    customer = await _create_customer(client, unique_suffix)
    plan = await _create_plan(client, rep["id"], unique_suffix)
    await _add_visit(client, plan["id"], customer["id"], customer["name"])
    await _confirm_plan(client, plan["id"])
    await _activate_plan(client, plan["id"])
    resp = await client.get(f"/api/plans/read/history?rep_id={rep['id']}")
    assert resp.status_code == 200
    rows = resp.json()
    row = next(
        (r for r in rows if str(r.get("plan_id") or r.get("id")) == str(plan["id"])),
        None,
    )
    assert row is not None
    assert row["status"] == "active"


@pytest.mark.anyio
async def test_plan_history_reflects_completed_status(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep")
    customer = await _create_customer(client, unique_suffix)
    plan = await _create_plan(client, rep["id"], unique_suffix)
    await _add_visit(client, plan["id"], customer["id"], customer["name"])
    await _confirm_plan(client, plan["id"])
    await _activate_plan(client, plan["id"])
    await _complete_plan(client, plan["id"])
    resp = await client.get(f"/api/plans/read/history?rep_id={rep['id']}")
    assert resp.status_code == 200
    rows = resp.json()
    row = next(
        (r for r in rows if str(r.get("plan_id") or r.get("id")) == str(plan["id"])),
        None,
    )
    assert row is not None
    assert row["status"] == "completed"


@pytest.mark.anyio
async def test_plan_history_date_filter_returns_matching_plans(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep")
    await _create_plan(client, rep["id"], unique_suffix)
    resp = await client.get(f"/api/plans/read/history?rep_id={rep['id']}&date=2025-06-01")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) >= 1
    assert all(str(r["date"]).startswith("2025-06-01") for r in rows)


@pytest.mark.anyio
async def test_plan_history_date_filter_no_match_returns_empty(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep")
    await _create_plan(client, rep["id"], unique_suffix)
    resp = await client.get(f"/api/plans/read/history?rep_id={rep['id']}&date=2099-01-01")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# GET /api/expenses/read/history
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_expense_history_reflects_rejected_status(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep", tag="rep")
    manager = await _create_user(client, unique_suffix, role="manager", tag="mgr")
    customer = await _create_customer(client, unique_suffix)
    plan = await _create_plan(client, rep["id"], unique_suffix)
    await _add_visit(client, plan["id"], customer["id"], customer["name"])
    await _confirm_plan(client, plan["id"])
    expense = await _create_expense(client, rep["id"], plan["id"], unique_suffix)
    await _submit_expense(client, expense["id"])
    await _reject_expense(client, expense["id"], manager["id"])
    resp = await client.get(f"/api/expenses/read/history?rep_id={rep['id']}")
    assert resp.status_code == 200
    rows = resp.json()
    row = next(
        (r for r in rows if str(r.get("expense_id") or r.get("id")) == str(expense["id"])),
        None,
    )
    assert row is not None
    assert row["status"] == "rejected"


@pytest.mark.anyio
async def test_expense_history_reflects_resubmitted_status(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep", tag="rep")
    manager = await _create_user(client, unique_suffix, role="manager", tag="mgr")
    customer = await _create_customer(client, unique_suffix)
    plan = await _create_plan(client, rep["id"], unique_suffix)
    await _add_visit(client, plan["id"], customer["id"], customer["name"])
    await _confirm_plan(client, plan["id"])
    expense = await _create_expense(client, rep["id"], plan["id"], unique_suffix)
    await _submit_expense(client, expense["id"])
    await _reject_expense(client, expense["id"], manager["id"])
    await client.patch(f"/api/expenses/{expense['id']}/resubmit", json={})
    resp = await client.get(f"/api/expenses/read/history?rep_id={rep['id']}")
    assert resp.status_code == 200
    rows = resp.json()
    row = next(
        (r for r in rows if str(r.get("expense_id") or r.get("id")) == str(expense["id"])),
        None,
    )
    assert row is not None
    assert row["status"] == "submitted"


@pytest.mark.anyio
async def test_expense_history_status_filter_returns_matching(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep", tag="rep")
    manager = await _create_user(client, unique_suffix, role="manager", tag="mgr")
    customer = await _create_customer(client, unique_suffix)
    plan = await _create_plan(client, rep["id"], unique_suffix)
    await _add_visit(client, plan["id"], customer["id"], customer["name"])
    await _confirm_plan(client, plan["id"])
    expense = await _create_expense(client, rep["id"], plan["id"], unique_suffix)
    await _submit_expense(client, expense["id"])
    await _approve_expense(client, expense["id"], manager["id"])
    resp = await client.get("/api/expenses/read/history?status=approved")
    assert resp.status_code == 200
    assert all(r["status"] == "approved" for r in resp.json())


@pytest.mark.anyio
async def test_expense_history_status_filter_approved_only(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep", tag="rep")
    manager = await _create_user(client, unique_suffix, role="manager", tag="mgr")
    customer = await _create_customer(client, unique_suffix)
    plan = await _create_plan(client, rep["id"], unique_suffix)
    await _add_visit(client, plan["id"], customer["id"], customer["name"])
    await _confirm_plan(client, plan["id"])
    expense1 = await _create_expense(client, rep["id"], plan["id"], unique_suffix + "a")
    expense2 = await _create_expense(client, rep["id"], plan["id"], unique_suffix + "b")
    await _submit_expense(client, expense1["id"])
    await _approve_expense(client, expense1["id"], manager["id"])
    await _submit_expense(client, expense2["id"])
    await _reject_expense(client, expense2["id"], manager["id"])
    resp = await client.get(f"/api/expenses/read/history?rep_id={rep['id']}&status=approved")
    assert resp.status_code == 200
    rows = resp.json()
    row_ids = [str(r.get("expense_id") or r.get("id")) for r in rows]
    assert str(expense1["id"]) in row_ids
    assert str(expense2["id"]) not in row_ids
