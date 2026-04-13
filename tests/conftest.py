"""Shared fixtures for the svp_mic integration test suite.

All tests interact with the running Docker stack at http://localhost
via nginx.  No service code is imported; all interaction is over HTTP.

Fixtures:
- client        -- session-scoped shared httpx.AsyncClient.
- unique_suffix -- session-scoped 8-hex-char random string.
- seed_users    -- session-scoped sales_rep and manager accounts.
- seed_customer -- session-scoped customer record.
- seed_plan     -- session-scoped day plan with one visit.
"""

import secrets

import httpx
import pytest


@pytest.fixture(scope="session")
async def client():
    """Yield a shared async HTTP client targeting the local nginx gateway.

    Return value:
    httpx.AsyncClient -- client with base_url set to http://localhost.
    """
    async with httpx.AsyncClient(base_url="http://localhost") as c:
        yield c


@pytest.fixture(scope="session")
def unique_suffix():
    """Return an 8-character hex string for unique resource naming.

    Generated once per test session so all fixtures share the same
    suffix and names stay consistent within a run.

    Return value:
    str -- random 8-character hexadecimal string.
    """
    return secrets.token_hex(4)


@pytest.fixture(scope="session")
async def seed_users(client, unique_suffix):
    """Create one sales_rep and one manager and yield their response data.

    Names and emails are derived from ``unique_suffix`` to avoid conflicts
    with other test runs or leftover data from previous runs.

    Yields:
    dict -- keys ``"rep"`` and ``"manager"``, each containing the full
            JSON response body of the created user.
    """
    rep_resp = await client.post(
        "/api/users",
        json={
            "name": f"Rep {unique_suffix}",
            "email": f"rep_{unique_suffix}@example.com",
            "password": "testpassword",
            "role": "sales_rep",
        },
    )
    rep_resp.raise_for_status()

    manager_resp = await client.post(
        "/api/users",
        json={
            "name": f"Manager {unique_suffix}",
            "email": f"manager_{unique_suffix}@example.com",
            "password": "testpassword",
            "role": "manager",
        },
    )
    manager_resp.raise_for_status()

    yield {"rep": rep_resp.json(), "manager": manager_resp.json()}


@pytest.fixture(scope="session")
async def seed_customer(client, unique_suffix):
    """Create one customer and yield the full response JSON.

    The customer name is derived from ``unique_suffix`` to avoid conflicts
    with other test runs or leftover data from previous runs.

    Yields:
    dict -- full JSON response body of the created customer.
    """
    resp = await client.post(
        "/api/customers",
        json={
            "name": f"Customer {unique_suffix}",
            "address": "1 Test Street",
        },
    )
    resp.raise_for_status()
    yield resp.json()


@pytest.fixture(scope="session")
async def seed_plan(client, seed_users, seed_customer):
    """Create a day plan for the rep with one visit and yield their data.

    The plan is created in ``draft`` state for the seeded sales rep.
    One visit targeting the seeded customer is added at scheduled
    position 1.

    Yields:
    dict -- keys ``"plan"`` and ``"visit"``, each containing the full
            JSON response body of the created resource.
    """
    rep_id = seed_users["rep"]["id"]
    customer_id = seed_customer["id"]
    customer_name = seed_customer["name"]

    plan_resp = await client.post(
        "/api/plans",
        json={"rep_id": rep_id, "date": "2026-04-14"},
    )
    plan_resp.raise_for_status()
    plan = plan_resp.json()

    visit_resp = await client.post(
        f"/api/plans/{plan['id']}/visits",
        json={
            "plan_id": plan["id"],
            "customer_id": customer_id,
            "customer_name": customer_name,
            "scheduled_order": 1,
        },
    )
    visit_resp.raise_for_status()

    yield {"plan": plan, "visit": visit_resp.json()}
