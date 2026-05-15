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


# ---------------------------------------------------------------------------
# PATCH /api/users/{id}
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_patch_user_updates_name(client, unique_suffix):
    user = await _create_user(client, unique_suffix)
    resp = await client.patch(
        f"/api/users/{user['id']}",
        json={"name": f"Updated {unique_suffix}"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"].startswith("Updated")


@pytest.mark.anyio
async def test_patch_user_updates_email(client, unique_suffix):
    user = await _create_user(client, unique_suffix)
    resp = await client.patch(
        f"/api/users/{user['id']}",
        json={"email": f"updated_{unique_suffix}@example.com"},
    )
    assert resp.status_code == 200
    assert "updated_" in resp.json()["email"]


@pytest.mark.anyio
async def test_patch_user_updates_role(client, unique_suffix):
    user = await _create_user(client, unique_suffix)
    resp = await client.patch(
        f"/api/users/{user['id']}",
        json={"role": "manager"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "manager"


@pytest.mark.anyio
async def test_patch_user_unknown_id_returns_404(client, unique_suffix):
    resp = await client.patch(
        f"/api/users/{uuid.uuid4()}",
        json={"name": "x"},
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_patch_user_duplicate_email_returns_409(client, unique_suffix):
    user1 = await _create_user(client, unique_suffix, tag="u1")
    user2 = await _create_user(client, unique_suffix, tag="u2")
    resp = await client.patch(
        f"/api/users/{user2['id']}",
        json={"email": user1["email"]},
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# DELETE /api/users/{id}
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_delete_user_with_administrator_returns_204(client, unique_suffix):
    admin = await _create_user(client, unique_suffix, role="administrator", tag="adm")
    rep = await _create_user(client, unique_suffix, role="sales_rep", tag="rep")
    resp = await client.delete(
        f"/api/users/{rep['id']}",
        headers={"X-User-Id": str(admin["id"])},
    )
    assert resp.status_code == 204


@pytest.mark.anyio
async def test_delete_user_without_header_returns_403(client, unique_suffix):
    user = await _create_user(client, unique_suffix)
    resp = await client.delete(f"/api/users/{user['id']}")
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_delete_user_with_non_administrator_returns_403(client, unique_suffix):
    manager = await _create_user(client, unique_suffix, role="manager", tag="mgr")
    rep = await _create_user(client, unique_suffix, role="sales_rep", tag="rep")
    resp = await client.delete(
        f"/api/users/{rep['id']}",
        headers={"X-User-Id": str(manager["id"])},
    )
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_delete_user_unknown_id_returns_404(client, unique_suffix):
    admin = await _create_user(client, unique_suffix, role="administrator")
    resp = await client.delete(
        f"/api/users/{uuid.uuid4()}",
        headers={"X-User-Id": str(admin["id"])},
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_get_user_after_delete_returns_404(client, unique_suffix):
    admin = await _create_user(client, unique_suffix, role="administrator", tag="adm")
    rep = await _create_user(client, unique_suffix, role="sales_rep", tag="rep")
    delete_resp = await client.delete(
        f"/api/users/{rep['id']}",
        headers={"X-User-Id": str(admin["id"])},
    )
    assert delete_resp.status_code == 204
    get_resp = await client.get(f"/api/users/{rep['id']}")
    assert get_resp.status_code == 404
