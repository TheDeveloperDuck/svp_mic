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


@pytest.mark.anyio
async def test_create_50_users(client, unique_suffix):
    resps = await asyncio.gather(*[
        client.post("/api/users", json={
            "name": f"User a {unique_suffix}{i}",
            "email": f"a{unique_suffix}{i}@example.com",
            "password": "pass",
            "role": "sales_rep",
        })
        for i in range(50)
    ])
    assert all(r.status_code == 201 for r in resps)


@pytest.mark.anyio
async def test_create_200_customers(client, unique_suffix):
    resps = await asyncio.gather(*[
        client.post("/api/customers", json={
            "name": f"Customer {unique_suffix}{i}",
            "address": f"Address {unique_suffix}{i}",
        })
        for i in range(200)
    ])
    assert all(r.status_code == 201 for r in resps)


@pytest.mark.anyio
async def test_list_customers_after_volume(client, unique_suffix):
    await asyncio.gather(*[
        client.post("/api/customers", json={
            "name": f"Customer {unique_suffix}{i}",
            "address": f"Address {unique_suffix}{i}",
        })
        for i in range(10)
    ])

    resp = await client.get("/api/customers")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.anyio
async def test_create_50_plans(client, unique_suffix):
    rep = await _create_user(client, unique_suffix)
    rep_id = rep["id"]

    resps = await asyncio.gather(*[
        client.post("/api/plans", json={
            "rep_id": rep_id,
            "date": "2025-06-01",
            "start_location": f"Start {unique_suffix}{i}",
            "end_location": f"End {unique_suffix}{i}",
        })
        for i in range(50)
    ])
    assert all(r.status_code == 201 for r in resps)


@pytest.mark.anyio
async def test_add_visits_to_plans(client, unique_suffix):
    rep = await _create_user(client, unique_suffix)
    rep_id = rep["id"]

    customer = await _create_customer(client, unique_suffix)
    customer_id = customer["id"]
    customer_name = customer["name"]

    plans = await asyncio.gather(*[
        _create_plan(client, rep_id, unique_suffix + str(i))
        for i in range(10)
    ])

    resps = await asyncio.gather(*[
        client.post(f"/api/plans/{plan['id']}/visits", json={
            "plan_id": plan["id"],
            "customer_id": customer_id,
            "customer_name": customer_name,
            "scheduled_order": 1,
        })
        for plan in plans
    ])
    assert all(r.status_code == 201 for r in resps)


@pytest.mark.anyio
async def test_confirm_plans(client, unique_suffix):
    rep = await _create_user(client, unique_suffix)
    rep_id = rep["id"]

    customer = await _create_customer(client, unique_suffix)
    customer_id = customer["id"]
    customer_name = customer["name"]

    plans = await asyncio.gather(*[
        _create_plan(client, rep_id, unique_suffix + str(i))
        for i in range(10)
    ])

    await asyncio.gather(*[
        client.post(f"/api/plans/{plan['id']}/visits", json={
            "plan_id": plan["id"],
            "customer_id": customer_id,
            "customer_name": customer_name,
            "scheduled_order": 1,
        })
        for plan in plans
    ])

    resps = await asyncio.gather(*[
        client.patch(f"/api/plans/{plan['id']}/confirm")
        for plan in plans
    ])
    assert all(r.status_code == 200 for r in resps)


@pytest.mark.anyio
async def test_create_100_expenses(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, tag="a")
    manager = await _create_user(client, unique_suffix, role="manager", tag="b")
    rep_id = rep["id"]

    customer = await _create_customer(client, unique_suffix)
    customer_id = customer["id"]

    plan = await _create_plan(client, rep_id, unique_suffix)
    plan_id = plan["id"]

    await _add_visit(client, plan_id, customer_id, customer["name"])
    await _confirm_plan(client, plan_id)

    resps = await asyncio.gather(*[
        client.post("/api/expenses", json={
            "rep_id": rep_id,
            "plan_id": plan_id,
            "category": "fuel",
            "amount": 50.00,
            "description": f"Expense {unique_suffix}{i}",
        })
        for i in range(100)
    ])
    assert all(r.status_code == 201 for r in resps)


@pytest.mark.anyio
async def test_list_expenses_after_volume(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, tag="a")
    manager = await _create_user(client, unique_suffix, role="manager", tag="b")
    rep_id = rep["id"]

    customer = await _create_customer(client, unique_suffix)
    customer_id = customer["id"]

    plan = await _create_plan(client, rep_id, unique_suffix)
    plan_id = plan["id"]

    await _add_visit(client, plan_id, customer_id, customer["name"])
    await _confirm_plan(client, plan_id)

    await asyncio.gather(*[
        client.post("/api/expenses", json={
            "rep_id": rep_id,
            "plan_id": plan_id,
            "category": "fuel",
            "amount": 50.00,
            "description": f"Expense {unique_suffix}{i}",
        })
        for i in range(20)
    ])

    resp = await client.get("/api/expenses")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.anyio
async def test_approve_expenses(client, unique_suffix):
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

    expenses = await asyncio.gather(*[
        _create_expense(client, rep_id, plan_id, unique_suffix + str(i))
        for i in range(10)
    ])

    await asyncio.gather(*[
        _submit_expense(client, e["id"])
        for e in expenses
    ])

    resps = await asyncio.gather(*[
        _approve_expense(client, e["id"], manager_id)
        for e in expenses
    ])
    assert all(r.status_code == 200 for r in resps)


@pytest.mark.anyio
async def test_plan_history_response_time(client, unique_suffix):
    rep = await _create_user(client, unique_suffix)
    rep_id = rep["id"]

    customer = await _create_customer(client, unique_suffix)
    customer_id = customer["id"]

    plans = await asyncio.gather(*[
        _create_plan(client, rep_id, unique_suffix + str(i))
        for i in range(5)
    ])

    await asyncio.gather(*[
        client.post(f"/api/plans/{plan['id']}/visits", json={
            "plan_id": plan["id"],
            "customer_id": customer_id,
            "customer_name": customer["name"],
            "scheduled_order": 1,
        })
        for plan in plans
    ])

    await asyncio.gather(*[
        client.patch(f"/api/plans/{plan['id']}/confirm")
        for plan in plans
    ])

    start = time.monotonic()
    resp = await client.get("/api/plans/read/history", params={"rep_id": rep_id})
    elapsed = time.monotonic() - start

    assert resp.status_code == 200
    assert elapsed < 3.0


@pytest.mark.anyio
async def test_expense_history_response_time(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, tag="a")
    manager = await _create_user(client, unique_suffix, role="manager", tag="b")
    rep_id = rep["id"]

    customer = await _create_customer(client, unique_suffix)
    customer_id = customer["id"]

    plan = await _create_plan(client, rep_id, unique_suffix)
    plan_id = plan["id"]

    await _add_visit(client, plan_id, customer_id, customer["name"])
    await _confirm_plan(client, plan_id)

    expenses = await asyncio.gather(*[
        _create_expense(client, rep_id, plan_id, unique_suffix + str(i))
        for i in range(10)
    ])

    await asyncio.gather(*[
        _submit_expense(client, e["id"])
        for e in expenses
    ])

    start = time.monotonic()
    resp = await client.get("/api/expenses/read/history", params={"rep_id": rep_id})
    elapsed = time.monotonic() - start

    assert resp.status_code == 200
    assert elapsed < 3.0


@pytest.mark.anyio
async def test_concurrent_full_lifecycle_5_reps(client, unique_suffix):
    async def _run_lifecycle(i):
        suffix = unique_suffix + str(i)
        rep = await _create_user(client, suffix, tag="r")
        manager = await _create_user(client, suffix, role="manager", tag="m")
        rep_id = rep["id"]
        manager_id = manager["id"]

        customer = await _create_customer(client, suffix)
        customer_id = customer["id"]

        plan = await _create_plan(client, rep_id, suffix)
        plan_id = plan["id"]

        visit_resp = await client.post(f"/api/plans/{plan_id}/visits", json={
            "plan_id": plan_id,
            "customer_id": customer_id,
            "customer_name": customer["name"],
            "scheduled_order": 1,
        })
        confirm_resp = await _confirm_plan(client, plan_id)
        activate_resp = await _activate_plan(client, plan_id)

        expense = await _create_expense(client, rep_id, plan_id, suffix)
        expense_id = expense["id"]

        submit_resp = await _submit_expense(client, expense_id)
        approve_resp = await _approve_expense(client, expense_id, manager_id)

        return [visit_resp, confirm_resp, activate_resp, submit_resp, approve_resp]

    all_resps = await asyncio.gather(*[_run_lifecycle(i) for i in range(5)])

    errors = [
        r for lifecycle in all_resps for r in lifecycle
        if r.status_code >= 400
    ]
    assert len(errors) == 0


@pytest.mark.anyio
async def test_deactivate_customers_with_plans(client, unique_suffix):
    rep = await _create_user(client, unique_suffix)
    rep_id = rep["id"]

    setups = await asyncio.gather(*[
        _create_customer(client, unique_suffix + str(i))
        for i in range(3)
    ])
    customers = list(setups)

    plans = await asyncio.gather(*[
        _create_plan(client, rep_id, unique_suffix + str(i))
        for i in range(3)
    ])

    await asyncio.gather(*[
        client.post(f"/api/plans/{plans[i]['id']}/visits", json={
            "plan_id": plans[i]["id"],
            "customer_id": customers[i]["id"],
            "customer_name": customers[i]["name"],
            "scheduled_order": 1,
        })
        for i in range(3)
    ])

    await asyncio.gather(*[
        client.patch(f"/api/plans/{plans[i]['id']}/confirm")
        for i in range(3)
    ])

    await asyncio.gather(*[
        client.patch(f"/api/customers/{customers[i]['id']}/deactivate")
        for i in range(3)
    ])

    plan_ids = [p["id"] for p in plans]
    for _ in range(30):
        await asyncio.sleep(1)
        resps = await asyncio.gather(*[
            client.get(f"/api/plans/{pid}")
            for pid in plan_ids
        ])
        statuses = [r.json()["status"] for r in resps]
        if all(s == "draft" for s in statuses):
            break

    resps = await asyncio.gather(*[
        client.get(f"/api/plans/{pid}")
        for pid in plan_ids
    ])
    assert all(r.json()["status"] == "draft" for r in resps)


@pytest.mark.anyio
async def test_cqrs_reflects_completed_for_plans(client, unique_suffix):
    rep = await _create_user(client, unique_suffix)
    rep_id = rep["id"]

    customer = await _create_customer(client, unique_suffix)
    customer_id = customer["id"]

    plans = await asyncio.gather(*[
        _create_plan(client, rep_id, unique_suffix + str(i))
        for i in range(3)
    ])

    await asyncio.gather(*[
        client.post(f"/api/plans/{plan['id']}/visits", json={
            "plan_id": plan["id"],
            "customer_id": customer_id,
            "customer_name": customer["name"],
            "scheduled_order": 1,
        })
        for plan in plans
    ])

    await asyncio.gather(*[
        client.patch(f"/api/plans/{plan['id']}/confirm")
        for plan in plans
    ])

    await asyncio.gather(*[
        client.patch(f"/api/plans/{plan['id']}/activate")
        for plan in plans
    ])

    await asyncio.gather(*[
        client.patch(f"/api/plans/{plan['id']}/complete")
        for plan in plans
    ])

    resp = await client.get("/api/plans/read/history", params={"rep_id": rep_id})
    assert resp.status_code == 200

    rows = resp.json()
    plan_ids = {p["id"] for p in plans}
    matched = [r for r in rows if r["id"] in plan_ids]
    assert len(matched) == 3
    assert all(r["status"] == "completed" for r in matched)
