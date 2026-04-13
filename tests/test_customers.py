"""Integration tests for the Customer endpoints of the Customer User Service.

Tests hit the running Docker stack at http://localhost via nginx.
No service code is imported; all interaction is over HTTP.

Endpoints under test:
- POST   /api/customers                    -- create a new customer.
- GET    /api/customers                    -- list all active customers.
- GET    /api/customers/{id}               -- fetch a single customer by ID.
- PATCH  /api/customers/{id}/deactivate    -- soft-delete a customer.

Test cases:
- test_create_customer -- valid creation returns 201 with correct fields.
- test_create_missing_name -- absent name field returns 422.
- test_create_missing_address -- absent address field returns 422.
- test_list_customers -- GET /api/customers returns 200 with a list body.
- test_get_customer_by_id -- known UUID returns 200 with matching id.
- test_get_customer_nonexistent -- unknown UUID returns 404.
- test_deactivate_customer -- deactivation returns 200 with is_active False.
- test_deactivate_already_inactive -- second deactivation returns 409.
"""

import uuid


async def test_create_customer(client, unique_suffix):
    """Create a customer with valid data and assert 201 with correct fields.

    Verifies that ``id``, ``name``, ``address``, ``is_active``, and
    ``is_priority`` are all present and have the expected values.
    """
    resp = await client.post(
        "/api/customers",
        json={
            "name": f"Acme {unique_suffix}",
            "address": "1 Test Street",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body
    assert body["name"] == f"Acme {unique_suffix}"
    assert body["address"] == "1 Test Street"
    assert body["is_active"] is True
    assert body["is_priority"] is False


async def test_create_missing_name(client, unique_suffix):
    """Omit the name field and assert the response is 422."""
    resp = await client.post(
        "/api/customers",
        json={"address": f"1 No-Name Street {unique_suffix}"},
    )
    assert resp.status_code == 422


async def test_create_missing_address(client, unique_suffix):
    """Omit the address field and assert the response is 422."""
    resp = await client.post(
        "/api/customers",
        json={"name": f"No Address Co {unique_suffix}"},
    )
    assert resp.status_code == 422


async def test_list_customers(client):
    """Fetch all customers and assert 200 with a list response body."""
    resp = await client.get("/api/customers")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_get_customer_by_id(client, unique_suffix):
    """Create a customer, fetch it by ID, and assert 200 with a matching id."""
    create_resp = await client.post(
        "/api/customers",
        json={
            "name": f"Fetchable Co {unique_suffix}",
            "address": "2 Fetch Lane",
        },
    )
    create_resp.raise_for_status()
    customer_id = create_resp.json()["id"]

    resp = await client.get(f"/api/customers/{customer_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == customer_id


async def test_get_customer_nonexistent(client):
    """Request a customer with a random UUID and assert 404."""
    resp = await client.get(f"/api/customers/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_deactivate_customer(client, unique_suffix):
    """Deactivate a customer and assert 200 with is_active set to False."""
    create_resp = await client.post(
        "/api/customers",
        json={
            "name": f"To Deactivate {unique_suffix}",
            "address": "3 Closing Road",
        },
    )
    create_resp.raise_for_status()
    customer_id = create_resp.json()["id"]

    resp = await client.patch(f"/api/customers/{customer_id}/deactivate")
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


async def test_deactivate_already_inactive(client, unique_suffix):
    """Deactivate a customer twice and assert the second request returns 409."""
    create_resp = await client.post(
        "/api/customers",
        json={
            "name": f"Double Deactivate {unique_suffix}",
            "address": "4 Repeat Avenue",
        },
    )
    create_resp.raise_for_status()
    customer_id = create_resp.json()["id"]

    first = await client.patch(f"/api/customers/{customer_id}/deactivate")
    first.raise_for_status()

    second = await client.patch(f"/api/customers/{customer_id}/deactivate")
    assert second.status_code == 409
