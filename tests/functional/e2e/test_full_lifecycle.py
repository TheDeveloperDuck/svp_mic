import asyncio
import subprocess
import time

import pytest


@pytest.fixture(scope="module", autouse=True)
def ensure_no_rate_limit():
    subprocess.run(
        ["kubectl", "delete", "-f", "k8s/istio/testing/rate-limit.yaml"],
        capture_output=True, check=False, timeout=30,
    )
    time.sleep(5)
    yield


async def _create_user(client, suffix, role="sales_rep", tag="a"):
    resp = await client.post("/api/users", json={
        "name": f"User {tag} {suffix}",
        "email": f"{tag}{suffix}@example.com",
        "password": "pass",
        "role": role,
    })
    return resp.json()


async def _create_customer(client, suffix):
    resp = await client.post("/api/customers", json={
        "name": f"Customer {suffix}",
        "address": f"Address {suffix}",
    })
    return resp.json()


async def _create_plan(client, rep_id, suffix):
    resp = await client.post("/api/plans", json={
        "rep_id": rep_id,
        "date": "2025-06-01",
        "start_location": f"Start {suffix}",
        "end_location": f"End {suffix}",
    })
    return resp.json()


async def _add_visit(client, plan_id, customer_id, customer_name, order=1):
    resp = await client.post(f"/api/plans/{plan_id}/visits", json={
        "plan_id": plan_id,
        "customer_id": customer_id,
        "customer_name": customer_name,
        "scheduled_order": order,
    })
    return resp.json()


async def _add_call(client, plan_id, customer_id, customer_name, order=1):
    resp = await client.post(f"/api/plans/{plan_id}/calls", json={
        "plan_id": plan_id,
        "customer_id": customer_id,
        "customer_name": customer_name,
        "scheduled_order": order,
    })
    return resp.json()


async def _confirm_plan(client, plan_id):
    return await client.patch(f"/api/plans/{plan_id}/confirm")


async def _activate_plan(client, plan_id):
    return await client.patch(f"/api/plans/{plan_id}/activate")


async def _complete_plan(client, plan_id):
    return await client.patch(f"/api/plans/{plan_id}/complete")


async def _create_expense(client, rep_id, plan_id, suffix):
    resp = await client.post("/api/expenses", json={
        "rep_id": rep_id,
        "plan_id": plan_id,
        "category": "fuel",
        "amount": 50.00,
        "description": f"Expense {suffix}",
    })
    return resp.json()


async def _submit_expense(client, expense_id):
    return await client.patch(f"/api/expenses/{expense_id}/submit")


async def _approve_expense(client, expense_id, manager_id):
    return await client.patch(f"/api/expenses/{expense_id}/approve", json={"manager_id": manager_id})


async def _reject_expense(client, expense_id, manager_id):
    return await client.patch(f"/api/expenses/{expense_id}/reject", json={"manager_id": manager_id})


@pytest.mark.anyio
async def test_full_sales_rep_lifecycle(client, unique_suffix):
    rep = await _create_user(client, unique_suffix)
    rep_id = rep["id"]

    customer = await _create_customer(client, unique_suffix)
    customer_id = customer["id"]

    plan = await _create_plan(client, rep_id, unique_suffix)
    plan_id = plan["id"]

    await _add_visit(client, plan_id, customer_id, customer["name"])
    await _confirm_plan(client, plan_id)
    await _activate_plan(client, plan_id)
    await _complete_plan(client, plan_id)

    resp = await client.get(f"/api/plans/{plan_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


@pytest.mark.anyio
async def test_full_expense_lifecycle(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, tag="a")
    manager = await _create_user(client, unique_suffix, role="manager", tag="b")
    rep_id = rep["id"]
    manager_id = manager["id"]

    customer = await _create_customer(client, unique_suffix)
    customer_id = customer["id"]

    plan = await _create_plan(client, rep_id, unique_suffix)
    plan_id = plan["id"]

    await _add_visit(client, plan_id, customer_id, customer["name"])
    await _confirm_plan(client, plan_id)

    expense = await _create_expense(client, rep_id, plan_id, unique_suffix)
    expense_id = expense["id"]

    await _submit_expense(client, expense_id)
    approve_resp = await _approve_expense(client, expense_id, manager_id)
    assert approve_resp.status_code == 200

    data = approve_resp.json()
    assert data["status"] == "approved"
    assert data["decided_at"] is not None


@pytest.mark.anyio
async def test_full_expense_rejection_and_resubmit(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, tag="a")
    manager = await _create_user(client, unique_suffix, role="manager", tag="b")
    rep_id = rep["id"]
    manager_id = manager["id"]

    customer = await _create_customer(client, unique_suffix)
    customer_id = customer["id"]

    plan = await _create_plan(client, rep_id, unique_suffix)
    plan_id = plan["id"]

    await _add_visit(client, plan_id, customer_id, customer["name"])
    await _confirm_plan(client, plan_id)

    expense = await _create_expense(client, rep_id, plan_id, unique_suffix)
    expense_id = expense["id"]

    await _submit_expense(client, expense_id)
    await _reject_expense(client, expense_id, manager_id)

    resubmit_resp = await client.patch(f"/api/expenses/{expense_id}/resubmit", json={})
    assert resubmit_resp.status_code == 200
    assert resubmit_resp.json()["status"] == "submitted"


@pytest.mark.anyio
async def test_manager_overview_reflects_lifecycle(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, tag="a")
    manager = await _create_user(client, unique_suffix, role="manager", tag="b")
    rep_id = rep["id"]
    manager_id = manager["id"]

    customer = await _create_customer(client, unique_suffix)
    customer_id = customer["id"]

    plan = await _create_plan(client, rep_id, unique_suffix)
    plan_id = plan["id"]

    await _add_visit(client, plan_id, customer_id, customer["name"])
    await _confirm_plan(client, plan_id)
    await _activate_plan(client, plan_id)
    await _complete_plan(client, plan_id)

    expense = await _create_expense(client, rep_id, plan_id, unique_suffix)
    expense_id = expense["id"]

    await _submit_expense(client, expense_id)
    await _approve_expense(client, expense_id, manager_id)

    resp = await client.get("/manager/overview")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


@pytest.mark.anyio
async def test_cqrs_reflects_all_transitions(client, unique_suffix):
    rep = await _create_user(client, unique_suffix)
    rep_id = rep["id"]

    customer = await _create_customer(client, unique_suffix)
    customer_id = customer["id"]

    plan = await _create_plan(client, rep_id, unique_suffix)
    plan_id = plan["id"]

    await _add_visit(client, plan_id, customer_id, customer["name"])
    await _confirm_plan(client, plan_id)
    await _activate_plan(client, plan_id)
    await _complete_plan(client, plan_id)

    resp = await client.get(f"/api/plans/read/history", params={"rep_id": rep_id})
    assert resp.status_code == 200

    rows = resp.json()
    row = next((r for r in rows if r["id"] == plan_id), None)
    assert row is not None
    assert row["status"] == "completed"
    assert row["visit_count"] >= 1


@pytest.mark.anyio
async def test_customer_deactivation_saga_confirmed_plan(client, unique_suffix):
    rep = await _create_user(client, unique_suffix)
    rep_id = rep["id"]

    customer = await _create_customer(client, unique_suffix)
    customer_id = customer["id"]

    plan = await _create_plan(client, rep_id, unique_suffix)
    plan_id = plan["id"]

    await _add_visit(client, plan_id, customer_id, customer["name"])
    await _confirm_plan(client, plan_id)

    deactivate_resp = await client.patch(f"/api/customers/{customer_id}/deactivate")
    assert deactivate_resp.status_code == 200

    for _ in range(20):
        await asyncio.sleep(1)
        resp = await client.get(f"/api/plans/{plan_id}")
        if resp.json()["status"] == "draft":
            break

    assert resp.json()["status"] == "draft"


@pytest.mark.anyio
async def test_customer_deactivation_saga_active_plan(client, unique_suffix):
    rep = await _create_user(client, unique_suffix)
    rep_id = rep["id"]

    customer = await _create_customer(client, unique_suffix)
    customer_id = customer["id"]

    plan = await _create_plan(client, rep_id, unique_suffix)
    plan_id = plan["id"]

    await _add_visit(client, plan_id, customer_id, customer["name"])
    await _confirm_plan(client, plan_id)
    await _activate_plan(client, plan_id)

    deactivate_resp = await client.patch(f"/api/customers/{customer_id}/deactivate")
    assert deactivate_resp.status_code == 200

    for _ in range(20):
        await asyncio.sleep(1)
        resp = await client.get(f"/api/plans/{plan_id}")
        if resp.json()["status"] == "draft":
            break

    assert resp.json()["status"] == "draft"


@pytest.mark.anyio
async def test_deactivation_with_no_plans(client, unique_suffix):
    customer = await _create_customer(client, unique_suffix)
    customer_id = customer["id"]

    resp = await client.patch(f"/api/customers/{customer_id}/deactivate")
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


@pytest.mark.anyio
async def test_plan_confirmation_with_active_customers(client, unique_suffix):
    rep = await _create_user(client, unique_suffix)
    rep_id = rep["id"]

    customer_a = await _create_customer(client, unique_suffix + "a")
    customer_b = await _create_customer(client, unique_suffix + "b")

    plan = await _create_plan(client, rep_id, unique_suffix)
    plan_id = plan["id"]

    await _add_visit(client, plan_id, customer_a["id"], customer_a["name"], order=1)
    await _add_visit(client, plan_id, customer_b["id"], customer_b["name"], order=2)

    confirm_resp = await _confirm_plan(client, plan_id)
    assert confirm_resp.status_code == 200

    resp = await client.get(f"/api/plans/{plan_id}")
    assert resp.json()["status"] == "confirmed"


@pytest.mark.anyio
async def test_plan_confirmation_rolls_back_when_customer_deactivated(client, unique_suffix):
    rep = await _create_user(client, unique_suffix)
    rep_id = rep["id"]

    customer = await _create_customer(client, unique_suffix)
    customer_id = customer["id"]

    plan = await _create_plan(client, rep_id, unique_suffix)
    plan_id = plan["id"]

    await _add_visit(client, plan_id, customer_id, customer["name"])
    await _confirm_plan(client, plan_id)

    deactivate_resp = await client.patch(f"/api/customers/{customer_id}/deactivate")
    assert deactivate_resp.status_code == 200

    for _ in range(20):
        await asyncio.sleep(1)
        resp = await client.get(f"/api/plans/{plan_id}")
        if resp.json()["status"] == "draft":
            break

    assert resp.json()["status"] == "draft"


@pytest.mark.anyio
async def test_full_admin_flow(client, unique_suffix):
    admin = await _create_user(client, unique_suffix, role="administrator", tag="a")
    admin_id = admin["id"]

    rep = await _create_user(client, unique_suffix, role="sales_rep", tag="b")
    rep_id = rep["id"]

    delete_resp = await client.delete(
        f"/api/users/{rep_id}",
        headers={"X-User-Id": str(admin_id)},
    )
    assert delete_resp.status_code == 204

    get_resp = await client.get(f"/api/users/{rep_id}")
    assert get_resp.status_code == 404
