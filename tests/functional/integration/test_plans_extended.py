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


async def _add_visit(client, plan_id, customer_id, customer_name, order=1):
    resp = await client.post(f"/api/plans/{plan_id}/visits", json={
        "plan_id": str(plan_id),
        "customer_id": str(customer_id),
        "customer_name": customer_name,
        "scheduled_order": order,
    })
    assert resp.status_code == 201
    return resp.json()


async def _add_call(client, plan_id, customer_id, customer_name, order=1):
    resp = await client.post(f"/api/plans/{plan_id}/calls", json={
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


# ---------------------------------------------------------------------------
# POST /api/plans/{plan_id}/calls
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_add_call_to_plan_returns_201(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep")
    customer = await _create_customer(client, unique_suffix)
    plan = await _create_plan(client, rep["id"], unique_suffix)
    resp = await client.post(f"/api/plans/{plan['id']}/calls", json={
        "plan_id": str(plan["id"]),
        "customer_id": str(customer["id"]),
        "customer_name": customer["name"],
        "scheduled_order": 1,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert "customer_id" in data
    assert "duration_minutes" in data


@pytest.mark.anyio
async def test_add_call_missing_customer_id_returns_422(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep")
    plan = await _create_plan(client, rep["id"], unique_suffix)
    resp = await client.post(f"/api/plans/{plan['id']}/calls", json={
        "customer_name": "Some Customer",
        "scheduled_order": 1,
    })
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_add_call_missing_scheduled_order_returns_422(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep")
    customer = await _create_customer(client, unique_suffix)
    plan = await _create_plan(client, rep["id"], unique_suffix)
    resp = await client.post(f"/api/plans/{plan['id']}/calls", json={
        "customer_id": str(customer["id"]),
        "customer_name": customer["name"],
    })
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_add_call_to_unknown_plan_returns_404(client, unique_suffix):
    resp = await client.post(f"/api/plans/{uuid.uuid4()}/calls", json={
        "plan_id": str(uuid.uuid4()),
        "customer_id": str(uuid.uuid4()),
        "customer_name": "Ghost Customer",
        "scheduled_order": 1,
    })
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/plans/{plan_id}/visits/{visit_id}
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_patch_visit_updates_status(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep")
    customer = await _create_customer(client, unique_suffix)
    plan = await _create_plan(client, rep["id"], unique_suffix)
    visit = await _add_visit(client, plan["id"], customer["id"], customer["name"])
    await _confirm_plan(client, plan["id"])
    await _activate_plan(client, plan["id"])
    resp = await client.patch(
        f"/api/plans/{plan['id']}/visits/{visit['id']}",
        json={"status": "completed", "outcome_notes": f"Notes {unique_suffix}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


@pytest.mark.anyio
async def test_patch_visit_updates_outcome_notes(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep")
    customer = await _create_customer(client, unique_suffix)
    plan = await _create_plan(client, rep["id"], unique_suffix)
    visit = await _add_visit(client, plan["id"], customer["id"], customer["name"])
    await _confirm_plan(client, plan["id"])
    await _activate_plan(client, plan["id"])
    resp = await client.patch(
        f"/api/plans/{plan['id']}/visits/{visit['id']}",
        json={"outcome_notes": f"Notes {unique_suffix}"},
    )
    assert resp.status_code == 200
    assert "Notes" in resp.json()["outcome_notes"]


@pytest.mark.anyio
async def test_patch_visit_unknown_id_returns_404(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep")
    customer = await _create_customer(client, unique_suffix)
    plan = await _create_plan(client, rep["id"], unique_suffix)
    await _add_visit(client, plan["id"], customer["id"], customer["name"])
    await _confirm_plan(client, plan["id"])
    await _activate_plan(client, plan["id"])
    resp = await client.patch(
        f"/api/plans/{plan['id']}/visits/{uuid.uuid4()}",
        json={"status": "completed"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/plans/{plan_id}/calls/{call_id}
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_patch_call_updates_status(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep")
    customer = await _create_customer(client, unique_suffix)
    plan = await _create_plan(client, rep["id"], unique_suffix)
    call = await _add_call(client, plan["id"], customer["id"], customer["name"])
    await _confirm_plan(client, plan["id"])
    await _activate_plan(client, plan["id"])
    resp = await client.patch(
        f"/api/plans/{plan['id']}/calls/{call['id']}",
        json={"status": "completed"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


@pytest.mark.anyio
async def test_patch_call_updates_outcome_notes(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep")
    customer = await _create_customer(client, unique_suffix)
    plan = await _create_plan(client, rep["id"], unique_suffix)
    call = await _add_call(client, plan["id"], customer["id"], customer["name"])
    await _confirm_plan(client, plan["id"])
    await _activate_plan(client, plan["id"])
    resp = await client.patch(
        f"/api/plans/{plan['id']}/calls/{call['id']}",
        json={"outcome_notes": f"Call notes {unique_suffix}"},
    )
    assert resp.status_code == 200
    assert "Call notes" in resp.json()["outcome_notes"]


@pytest.mark.anyio
async def test_patch_call_unknown_id_returns_404(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep")
    customer = await _create_customer(client, unique_suffix)
    plan = await _create_plan(client, rep["id"], unique_suffix)
    await _add_call(client, plan["id"], customer["id"], customer["name"])
    await _confirm_plan(client, plan["id"])
    await _activate_plan(client, plan["id"])
    resp = await client.patch(
        f"/api/plans/{plan['id']}/calls/{uuid.uuid4()}",
        json={"status": "completed"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# State machine transition errors
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_activate_completed_plan_returns_409(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep")
    customer = await _create_customer(client, unique_suffix)
    plan = await _create_plan(client, rep["id"], unique_suffix)
    await _add_visit(client, plan["id"], customer["id"], customer["name"])
    await _confirm_plan(client, plan["id"])
    await _activate_plan(client, plan["id"])
    await _complete_plan(client, plan["id"])
    resp = await _activate_plan(client, plan["id"])
    assert resp.status_code == 409


@pytest.mark.anyio
async def test_complete_confirmed_plan_returns_409(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep")
    customer = await _create_customer(client, unique_suffix)
    plan = await _create_plan(client, rep["id"], unique_suffix)
    await _add_visit(client, plan["id"], customer["id"], customer["name"])
    await _confirm_plan(client, plan["id"])
    resp = await _complete_plan(client, plan["id"])
    assert resp.status_code == 409


@pytest.mark.anyio
async def test_complete_already_completed_plan_returns_409(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep")
    customer = await _create_customer(client, unique_suffix)
    plan = await _create_plan(client, rep["id"], unique_suffix)
    await _add_visit(client, plan["id"], customer["id"], customer["name"])
    await _confirm_plan(client, plan["id"])
    await _activate_plan(client, plan["id"])
    await _complete_plan(client, plan["id"])
    resp = await _complete_plan(client, plan["id"])
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# POST /api/plans/{plan_id}/visits — state guard
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_add_visit_to_confirmed_plan_returns_409(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep")
    customer = await _create_customer(client, unique_suffix)
    plan = await _create_plan(client, rep["id"], unique_suffix)
    await _add_visit(client, plan["id"], customer["id"], customer["name"])
    await _confirm_plan(client, plan["id"])
    resp = await client.post(f"/api/plans/{plan['id']}/visits", json={
        "plan_id": str(plan["id"]),
        "customer_id": str(customer["id"]),
        "customer_name": customer["name"],
        "scheduled_order": 2,
    })
    assert resp.status_code == 409


@pytest.mark.anyio
async def test_add_visit_to_active_plan_returns_409(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep")
    customer = await _create_customer(client, unique_suffix)
    plan = await _create_plan(client, rep["id"], unique_suffix)
    await _add_visit(client, plan["id"], customer["id"], customer["name"])
    await _confirm_plan(client, plan["id"])
    await _activate_plan(client, plan["id"])
    resp = await client.post(f"/api/plans/{plan['id']}/visits", json={
        "plan_id": str(plan["id"]),
        "customer_id": str(customer["id"]),
        "customer_name": customer["name"],
        "scheduled_order": 2,
    })
    assert resp.status_code == 409


@pytest.mark.anyio
async def test_add_visit_to_completed_plan_returns_409(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep")
    customer = await _create_customer(client, unique_suffix)
    plan = await _create_plan(client, rep["id"], unique_suffix)
    await _add_visit(client, plan["id"], customer["id"], customer["name"])
    await _confirm_plan(client, plan["id"])
    await _activate_plan(client, plan["id"])
    await _complete_plan(client, plan["id"])
    resp = await client.post(f"/api/plans/{plan['id']}/visits", json={
        "plan_id": str(plan["id"]),
        "customer_id": str(customer["id"]),
        "customer_name": customer["name"],
        "scheduled_order": 2,
    })
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# GET /api/plans
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_list_plans_filtered_by_rep_id(client, unique_suffix):
    rep1 = await _create_user(client, unique_suffix, role="sales_rep", tag="r1")
    rep2 = await _create_user(client, unique_suffix, role="sales_rep", tag="r2")
    await _create_plan(client, rep1["id"], unique_suffix + "a")
    await _create_plan(client, rep2["id"], unique_suffix + "b")
    resp = await client.get(f"/api/plans?rep_id={rep1['id']}")
    assert resp.status_code == 200
    plans = resp.json()
    assert len(plans) >= 1
    assert all(p["rep_id"] == str(rep1["id"]) for p in plans)


# ---------------------------------------------------------------------------
# PATCH /api/plans/{plan_id}/confirm — calls only
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_confirm_plan_with_only_calls_returns_200(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep")
    customer = await _create_customer(client, unique_suffix)
    plan = await _create_plan(client, rep["id"], unique_suffix)
    await _add_call(client, plan["id"], customer["id"], customer["name"])
    resp = await _confirm_plan(client, plan["id"])
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed"
