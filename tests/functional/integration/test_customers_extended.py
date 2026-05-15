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


# ---------------------------------------------------------------------------
# PATCH /api/customers/{id}
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_patch_customer_updates_name(client, unique_suffix):
    customer = await _create_customer(client, unique_suffix)
    resp = await client.patch(
        f"/api/customers/{customer['id']}",
        json={"name": f"Updated Name {unique_suffix}"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"].startswith("Updated Name")


@pytest.mark.anyio
async def test_patch_customer_updates_address(client, unique_suffix):
    customer = await _create_customer(client, unique_suffix)
    resp = await client.patch(
        f"/api/customers/{customer['id']}",
        json={"address": f"New Address {unique_suffix}"},
    )
    assert resp.status_code == 200
    assert resp.json()["address"].startswith("New Address")


@pytest.mark.anyio
async def test_patch_customer_updates_lat_lng(client, unique_suffix):
    customer = await _create_customer(client, unique_suffix)
    resp = await client.patch(
        f"/api/customers/{customer['id']}",
        json={"lat": 53.3498, "lng": -6.2603},
    )
    assert resp.status_code == 200
    assert resp.json()["lat"] == 53.3498
    assert resp.json()["lng"] == -6.2603


@pytest.mark.anyio
async def test_patch_customer_updates_assigned_rep_id(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep")
    customer = await _create_customer(client, unique_suffix)
    resp = await client.patch(
        f"/api/customers/{customer['id']}",
        json={"assigned_rep_id": str(rep["id"])},
    )
    assert resp.status_code == 200
    assert resp.json()["assigned_rep_id"] == str(rep["id"])


@pytest.mark.anyio
async def test_patch_customer_unknown_id_returns_404(client, unique_suffix):
    resp = await client.patch(
        f"/api/customers/{uuid.uuid4()}",
        json={"name": "x"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/customers/{id}/flag
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_flag_customer_with_manager_sets_priority(client, unique_suffix):
    manager = await _create_user(client, unique_suffix, role="manager")
    customer = await _create_customer(client, unique_suffix)
    resp = await client.patch(
        f"/api/customers/{customer['id']}/flag",
        headers={"X-User-Id": str(manager["id"])},
    )
    assert resp.status_code == 200
    assert resp.json()["is_priority"] is True


@pytest.mark.anyio
async def test_flag_customer_without_header_returns_403(client, unique_suffix):
    customer = await _create_customer(client, unique_suffix)
    resp = await client.patch(f"/api/customers/{customer['id']}/flag")
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_flag_customer_with_sales_rep_returns_403(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep")
    customer = await _create_customer(client, unique_suffix)
    resp = await client.patch(
        f"/api/customers/{customer['id']}/flag",
        headers={"X-User-Id": str(rep["id"])},
    )
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_flag_customer_with_invalid_uuid_header_returns_400(client, unique_suffix):
    customer = await _create_customer(client, unique_suffix)
    resp = await client.patch(
        f"/api/customers/{customer['id']}/flag",
        headers={"X-User-Id": "not-a-uuid"},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# PATCH /api/customers/{id}/assign
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_assign_customer_to_rep(client, unique_suffix):
    rep = await _create_user(client, unique_suffix, role="sales_rep")
    customer = await _create_customer(client, unique_suffix)
    resp = await client.patch(
        f"/api/customers/{customer['id']}/assign",
        json={"rep_id": str(rep["id"])},
    )
    assert resp.status_code == 200
    assert resp.json()["assigned_rep_id"] == str(rep["id"])


@pytest.mark.anyio
async def test_assign_customer_unknown_id_returns_404(client, unique_suffix):
    resp = await client.patch(
        f"/api/customers/{uuid.uuid4()}/assign",
        json={"rep_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404
