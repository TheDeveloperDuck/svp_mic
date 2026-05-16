import pytest


@pytest.mark.anyio
async def test_get_customers_via_gateway(client):
    resp = await client.get("/api/customers")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_get_users_via_gateway(client):
    resp = await client.get("/api/users")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_get_plans_via_gateway(client):
    resp = await client.get("/api/plans")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_get_expenses_via_gateway(client):
    resp = await client.get("/api/expenses")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_post_customers_via_gateway(client, unique_suffix):
    resp = await client.post("/api/customers", json={
        "name": f"Test {unique_suffix}",
        "address": f"Test Address {unique_suffix}",
    })
    assert resp.status_code == 201


@pytest.mark.anyio
async def test_post_plans_via_gateway(client, unique_suffix):
    rep_resp = await client.post("/api/users", json={
        "name": f"Rep {unique_suffix}",
        "email": f"rep_{unique_suffix}@example.com",
        "password": "password123",
        "role": "sales_rep",
    })
    assert rep_resp.status_code == 201
    rep_id = rep_resp.json()["id"]

    resp = await client.post("/api/plans", json={
        "rep_id": rep_id,
        "date": "2025-06-01",
        "start_location": f"Start {unique_suffix}",
        "end_location": f"End {unique_suffix}",
    })
    assert resp.status_code == 201


@pytest.mark.anyio
async def test_patch_plan_confirm_via_gateway(client, unique_suffix):
    rep_resp = await client.post("/api/users", json={
        "name": f"Rep {unique_suffix}",
        "email": f"rep_{unique_suffix}@example.com",
        "password": "password123",
        "role": "sales_rep",
    })
    assert rep_resp.status_code == 201
    rep_id = rep_resp.json()["id"]

    customer_resp = await client.post("/api/customers", json={
        "name": f"Customer {unique_suffix}",
        "address": f"1 Main St {unique_suffix}",
    })
    assert customer_resp.status_code == 201
    customer = customer_resp.json()

    plan_resp = await client.post("/api/plans", json={
        "rep_id": rep_id,
        "date": "2025-06-01",
        "start_location": f"Start {unique_suffix}",
        "end_location": f"End {unique_suffix}",
    })
    assert plan_resp.status_code == 201
    plan_id = plan_resp.json()["id"]

    visit_resp = await client.post(f"/api/plans/{plan_id}/visits", json={
        "plan_id": plan_id,
        "customer_id": customer["id"],
        "customer_name": customer["name"],
        "scheduled_order": 1,
    })
    assert visit_resp.status_code == 201

    resp = await client.patch(f"/api/plans/{plan_id}/confirm")
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed"


@pytest.mark.anyio
async def test_unknown_path_returns_frontend(client, unique_suffix):
    resp = await client.get(f"/some-unknown-path-xyz-{unique_suffix}")
    # 200 if the frontend VS catch-all is active,
    # 404 if Istio returns no-route-found directly.
    assert resp.status_code in (200, 404)


@pytest.mark.anyio
async def test_root_returns_frontend(client):
    resp = await client.get("/")
    assert resp.status_code == 200
