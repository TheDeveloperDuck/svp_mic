"""Integration tests for the User endpoints of the Customer User Service.

Tests hit the running Docker stack at http://localhost via nginx.
No service code is imported; all interaction is over HTTP.

Endpoints under test:
- POST   /api/users           -- create a new user account.
- GET    /api/users           -- list all users.
- GET    /api/users/{user_id} -- fetch a single user by ID.

Test cases:
- test_create_sales_rep -- valid creation returns 201 with correct fields.
- test_create_manager -- valid creation returns 201 with correct fields.
- test_create_duplicate_email -- duplicate email returns 409.
- test_create_missing_name -- absent name field returns 422.
- test_create_missing_email -- absent email field returns 422.
- test_create_missing_password -- absent password field returns 422.
- test_create_missing_role -- absent role field returns 422.
- test_create_invalid_role -- unrecognised role value returns 422.
- test_list_users -- GET /api/users returns 200 with a list body.
- test_get_user_by_id -- known UUID returns 200 with matching id.
- test_get_user_nonexistent -- unknown UUID returns 404.
"""

import uuid


async def test_create_sales_rep(client, unique_suffix):
    """Create a sales_rep user and assert 201 with correct response fields.

    Verifies that ``id``, ``name``, ``email``, ``role``, and ``is_active``
    are all present and have the expected values.
    """
    resp = await client.post(
        "/api/users",
        json={
            "name": f"Sales Rep {unique_suffix}",
            "email": f"salesrep_{unique_suffix}@example.com",
            "password": "testpassword",
            "role": "sales_rep",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body
    assert body["name"] == f"Sales Rep {unique_suffix}"
    assert body["email"] == f"salesrep_{unique_suffix}@example.com"
    assert body["role"] == "sales_rep"
    assert body["is_active"] is True


async def test_create_manager(client, unique_suffix):
    """Create a manager user and assert 201 with correct response fields.

    Verifies that ``id``, ``name``, ``email``, ``role``, and ``is_active``
    are all present and have the expected values.
    """
    resp = await client.post(
        "/api/users",
        json={
            "name": f"Manager {unique_suffix}",
            "email": f"manager_{unique_suffix}@example.com",
            "password": "testpassword",
            "role": "manager",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body
    assert body["name"] == f"Manager {unique_suffix}"
    assert body["email"] == f"manager_{unique_suffix}@example.com"
    assert body["role"] == "manager"
    assert body["is_active"] is True


async def test_create_duplicate_email(client, unique_suffix):
    """Submit the same email address twice and assert the second returns 409."""
    payload = {
        "name": f"Dup User {unique_suffix}",
        "email": f"dup_{unique_suffix}@example.com",
        "password": "testpassword",
        "role": "sales_rep",
    }
    first = await client.post("/api/users", json=payload)
    first.raise_for_status()

    second = await client.post("/api/users", json=payload)
    assert second.status_code == 409


async def test_create_missing_name(client, unique_suffix):
    """Omit the name field and assert the response is 422."""
    resp = await client.post(
        "/api/users",
        json={
            "email": f"noname_{unique_suffix}@example.com",
            "password": "testpassword",
            "role": "sales_rep",
        },
    )
    assert resp.status_code == 422


async def test_create_missing_email(client, unique_suffix):
    """Omit the email field and assert the response is 422."""
    resp = await client.post(
        "/api/users",
        json={
            "name": f"No Email {unique_suffix}",
            "password": "testpassword",
            "role": "sales_rep",
        },
    )
    assert resp.status_code == 422


async def test_create_missing_password(client, unique_suffix):
    """Omit the password field and assert the response is 422."""
    resp = await client.post(
        "/api/users",
        json={
            "name": f"No Password {unique_suffix}",
            "email": f"nopw_{unique_suffix}@example.com",
            "role": "sales_rep",
        },
    )
    assert resp.status_code == 422


async def test_create_missing_role(client, unique_suffix):
    """Omit the role field and assert the response is 422."""
    resp = await client.post(
        "/api/users",
        json={
            "name": f"No Role {unique_suffix}",
            "email": f"norole_{unique_suffix}@example.com",
            "password": "testpassword",
        },
    )
    assert resp.status_code == 422


async def test_create_invalid_role(client, unique_suffix):
    """Supply an unrecognised role value and assert the response is 422."""
    resp = await client.post(
        "/api/users",
        json={
            "name": f"Bad Role {unique_suffix}",
            "email": f"badrole_{unique_suffix}@example.com",
            "password": "testpassword",
            "role": "invalid_role",
        },
    )
    assert resp.status_code == 422


async def test_list_users(client):
    """Fetch all users and assert 200 with a list response body."""
    resp = await client.get("/api/users")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_get_user_by_id(client, unique_suffix):
    """Create a user, fetch it by ID, and assert 200 with a matching id."""
    create_resp = await client.post(
        "/api/users",
        json={
            "name": f"Fetchable {unique_suffix}",
            "email": f"fetchable_{unique_suffix}@example.com",
            "password": "testpassword",
            "role": "sales_rep",
        },
    )
    create_resp.raise_for_status()
    user_id = create_resp.json()["id"]

    resp = await client.get(f"/api/users/{user_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == user_id


async def test_get_user_nonexistent(client):
    """Request a user with a random UUID and assert 404."""
    resp = await client.get(f"/api/users/{uuid.uuid4()}")
    assert resp.status_code == 404
