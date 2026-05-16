"""Regression tests porting the original Docker Compose suite to run
against the Kubernetes cluster via the Istio ingressgateway at
http://localhost:8080.

The original tests targeted http://localhost via nginx.  The only
structural changes from the originals are:

- Every test function carries ``@pytest.mark.anyio``.
- Saga polling uses 20 attempts at 1 s intervals (up from 10 at 0.5 s)
  to accommodate the K8s outbox poller cycle (5 s) and Kafka consumer lag.
- ``client`` and ``unique_suffix`` come from tests/functional/conftest.py.
- ``seed_users``, ``seed_customer``, and ``seed_plan`` are defined here.

Total: 75 tests across users (11), customers (8), plans (17),
expenses (14), CQRS (8), edge cases (13), and saga (4).
"""

import asyncio
import secrets
import uuid

import pytest


# ---------------------------------------------------------------------------
# Seed fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
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


@pytest.fixture
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


@pytest.fixture
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
        json={
            "rep_id": rep_id,
            "date": "2026-04-14",
            "start_location": "Dublin",
            "end_location": "Cork",
        },
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_plan(client, rep_id: str) -> dict:
    """Create a day plan for the given rep and return the response body.

    Arguments:
    client -- active httpx.AsyncClient.
    rep_id -- UUID string of the sales rep.

    Return value:
    dict -- full JSON response body of the created plan.
    """
    resp = await client.post(
        "/api/plans",
        json={
            "rep_id": rep_id,
            "date": "2026-04-15",
            "start_location": "Dublin",
            "end_location": "Cork",
        },
    )
    resp.raise_for_status()
    return resp.json()


async def _add_visit(
    client,
    plan_id: str,
    customer_id: str,
    customer_name: str,
    scheduled_order: int = 1,
) -> dict:
    """Add a visit to a plan and return the response body.

    Arguments:
    client          -- active httpx.AsyncClient.
    plan_id         -- UUID string of the parent plan.
    customer_id     -- UUID string of the customer.
    customer_name   -- display name of the customer.
    scheduled_order -- position in the visit sequence (default 1).

    Return value:
    dict -- full JSON response body of the created visit.
    """
    resp = await client.post(
        f"/api/plans/{plan_id}/visits",
        json={
            "plan_id": plan_id,
            "customer_id": customer_id,
            "customer_name": customer_name,
            "scheduled_order": scheduled_order,
        },
    )
    resp.raise_for_status()
    return resp.json()


async def _confirm_plan(client, plan_id: str) -> dict:
    """Confirm a plan and return the response body.

    Arguments:
    client  -- active httpx.AsyncClient.
    plan_id -- UUID string of the plan to confirm.

    Return value:
    dict -- full JSON response body of the updated plan.
    """
    resp = await client.patch(f"/api/plans/{plan_id}/confirm")
    resp.raise_for_status()
    return resp.json()


async def _activate_plan(client, plan_id: str) -> dict:
    """Activate a plan and return the response body.

    Arguments:
    client  -- active httpx.AsyncClient.
    plan_id -- UUID string of the plan to activate.

    Return value:
    dict -- full JSON response body of the updated plan.
    """
    resp = await client.patch(f"/api/plans/{plan_id}/activate")
    resp.raise_for_status()
    return resp.json()


async def _create_expense(client, rep_id: str, plan_id: str) -> dict:
    """Create an expense submission and return the response body.

    Arguments:
    client  -- active httpx.AsyncClient.
    rep_id  -- UUID string of the sales rep.
    plan_id -- UUID string of the associated day plan.

    Return value:
    dict -- full JSON response body of the created expense.
    """
    resp = await client.post(
        "/api/expenses",
        json={
            "rep_id": rep_id,
            "plan_id": plan_id,
            "category": "fuel",
            "amount": "25.50",
            "description": "Motorway fuel",
        },
    )
    resp.raise_for_status()
    return resp.json()


async def _submit_expense(client, expense_id: str) -> dict:
    """Submit an expense for approval and return the response body.

    Arguments:
    client     -- active httpx.AsyncClient.
    expense_id -- UUID string of the expense to submit.

    Return value:
    dict -- full JSON response body of the updated expense.
    """
    resp = await client.patch(f"/api/expenses/{expense_id}/submit")
    resp.raise_for_status()
    return resp.json()


async def _approve_expense(client, expense_id: str, manager_id: str) -> dict:
    """Approve a pending expense and return the response body.

    Arguments:
    client     -- active httpx.AsyncClient.
    expense_id -- UUID string of the expense to approve.
    manager_id -- UUID string of the approving manager.

    Return value:
    dict -- full JSON response body of the updated expense.
    """
    resp = await client.patch(
        f"/api/expenses/{expense_id}/approve",
        json={"manager_id": manager_id},
    )
    resp.raise_for_status()
    return resp.json()


async def _reject_expense(client, expense_id: str, manager_id: str) -> dict:
    """Reject a pending expense and return the response body.

    Arguments:
    client     -- active httpx.AsyncClient.
    expense_id -- UUID string of the expense to reject.
    manager_id -- UUID string of the rejecting manager.

    Return value:
    dict -- full JSON response body of the updated expense.
    """
    resp = await client.patch(
        f"/api/expenses/{expense_id}/reject",
        json={"manager_id": manager_id},
    )
    resp.raise_for_status()
    return resp.json()


async def _create_user(client, role: str) -> dict:
    """Create a user with the given role and return the response body.

    Arguments:
    client -- active httpx.AsyncClient.
    role   -- role string, e.g. ``"sales_rep"`` or ``"manager"``.

    Return value:
    dict -- full JSON response body of the created user.
    """
    suffix = secrets.token_hex(4)
    resp = await client.post(
        "/api/users",
        json={
            "name": f"User {suffix}",
            "email": f"user_{suffix}@example.com",
            "password": "testpassword",
            "role": role,
        },
    )
    resp.raise_for_status()
    return resp.json()


async def _create_customer(client) -> dict:
    """Create a customer and return the response body.

    Arguments:
    client -- active httpx.AsyncClient.

    Return value:
    dict -- full JSON response body of the created customer.
    """
    suffix = secrets.token_hex(4)
    resp = await client.post(
        "/api/customers",
        json={"name": f"Customer {suffix}", "address": "1 Test Street"},
    )
    resp.raise_for_status()
    return resp.json()


async def _deactivate_customer(client, customer_id: str) -> dict:
    """Deactivate a customer and return the response body.

    Arguments:
    client      -- active httpx.AsyncClient.
    customer_id -- UUID string of the customer to deactivate.

    Return value:
    dict -- full JSON response body of the deactivated customer.
    """
    resp = await client.patch(f"/api/customers/{customer_id}/deactivate")
    resp.raise_for_status()
    return resp.json()


async def _poll_plan_status(
    client,
    plan_id: str,
    target_status: str,
    *,
    attempts: int = 20,
    interval: float = 1.0,
) -> str:
    """Poll GET /api/plans/{plan_id} until the status matches or attempts run out.

    Arguments:
    client        -- active httpx.AsyncClient.
    plan_id       -- UUID string of the plan to poll.
    target_status -- status value to wait for.
    attempts      -- maximum number of polling attempts (default 20).
    interval      -- seconds to wait between attempts (default 1.0).

    Return value:
    str -- the plan status observed on the final attempt.
    """
    status = None
    for _ in range(attempts):
        resp = await client.get(f"/api/plans/{plan_id}")
        resp.raise_for_status()
        status = resp.json()["status"]
        if status == target_status:
            break
        await asyncio.sleep(interval)
    return status


def _find_by_id(rows: list, resource_id: str) -> dict | None:
    """Return the first row whose ``id`` matches resource_id, or ``None``.

    Arguments:
    rows        -- list of dicts from a read-model response.
    resource_id -- UUID string to search for.

    Return value:
    dict | None -- the matching row, or ``None`` if not found.
    """
    return next((r for r in rows if r["id"] == resource_id), None)


# ---------------------------------------------------------------------------
# User tests (11)
# ---------------------------------------------------------------------------

class TestUsers:

    @pytest.mark.anyio
    async def test_create_sales_rep(self, client, unique_suffix):
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

    @pytest.mark.anyio
    async def test_create_manager(self, client, unique_suffix):
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

    @pytest.mark.anyio
    async def test_create_duplicate_email(self, client, unique_suffix):
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

    @pytest.mark.anyio
    async def test_create_missing_name(self, client, unique_suffix):
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

    @pytest.mark.anyio
    async def test_create_missing_email(self, client, unique_suffix):
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

    @pytest.mark.anyio
    async def test_create_missing_password(self, client, unique_suffix):
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

    @pytest.mark.anyio
    async def test_create_missing_role(self, client, unique_suffix):
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

    @pytest.mark.anyio
    async def test_create_invalid_role(self, client, unique_suffix):
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

    @pytest.mark.anyio
    async def test_list_users(self, client):
        """Fetch all users and assert 200 with a list response body."""
        resp = await client.get("/api/users")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.anyio
    async def test_get_user_by_id(self, client, unique_suffix):
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

    @pytest.mark.anyio
    async def test_get_user_nonexistent(self, client):
        """Request a user with a random UUID and assert 404."""
        resp = await client.get(f"/api/users/{uuid.uuid4()}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Customer tests (8)
# ---------------------------------------------------------------------------

class TestCustomers:

    @pytest.mark.anyio
    async def test_create_customer(self, client, unique_suffix):
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

    @pytest.mark.anyio
    async def test_create_customer_missing_name(self, client, unique_suffix):
        """Omit the name field and assert the response is 422."""
        resp = await client.post(
            "/api/customers",
            json={"address": f"1 No-Name Street {unique_suffix}"},
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_create_missing_address(self, client, unique_suffix):
        """Omit the address field and assert the response is 422."""
        resp = await client.post(
            "/api/customers",
            json={"name": f"No Address Co {unique_suffix}"},
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_list_customers(self, client):
        """Fetch all customers and assert 200 with a list response body."""
        resp = await client.get("/api/customers")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.anyio
    async def test_get_customer_by_id(self, client, unique_suffix):
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

    @pytest.mark.anyio
    async def test_get_customer_nonexistent(self, client):
        """Request a customer with a random UUID and assert 404."""
        resp = await client.get(f"/api/customers/{uuid.uuid4()}")
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_deactivate_customer(self, client, unique_suffix):
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

    @pytest.mark.anyio
    async def test_deactivate_already_inactive(self, client, unique_suffix):
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


# ---------------------------------------------------------------------------
# Plan tests (17)
# ---------------------------------------------------------------------------

class TestPlans:

    @pytest.mark.anyio
    async def test_create_plan_valid(self, client, seed_users):
        """Create a plan with a valid rep_id and assert 201 with status ``draft``.

        Verifies that ``id``, ``rep_id``, ``date``, and ``status`` are all
        present and have the expected values.
        """
        rep_id = seed_users["rep"]["id"]
        resp = await client.post(
            "/api/plans",
            json={
                "rep_id": rep_id,
                "date": "2026-04-15",
                "start_location": "Dublin",
                "end_location": "Cork",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "id" in body
        assert body["rep_id"] == rep_id
        assert body["date"] == "2026-04-15"
        assert body["status"] == "draft"

    @pytest.mark.anyio
    async def test_create_plan_nonexistent_rep_id(self, client):
        """Submit a random rep UUID and assert the response is 404 or 422."""
        resp = await client.post(
            "/api/plans",
            json={"rep_id": str(uuid.uuid4()), "date": "2026-04-15"},
        )
        assert resp.status_code in (404, 422)

    @pytest.mark.anyio
    async def test_create_plan_missing_date(self, client, seed_users):
        """Omit the date field and assert the response is 422."""
        rep_id = seed_users["rep"]["id"]
        resp = await client.post(
            "/api/plans",
            json={"rep_id": rep_id},
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_create_plan_missing_start_location(self, client, seed_users):
        """Omit the start_location field and assert the response is 422."""
        rep_id = seed_users["rep"]["id"]
        resp = await client.post(
            "/api/plans",
            json={"rep_id": rep_id, "date": "2026-04-15", "end_location": "Cork"},
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_create_plan_missing_end_location(self, client, seed_users):
        """Omit the end_location field and assert the response is 422."""
        rep_id = seed_users["rep"]["id"]
        resp = await client.post(
            "/api/plans",
            json={"rep_id": rep_id, "date": "2026-04-15", "start_location": "Dublin"},
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_add_visit(self, client, seed_users, seed_customer):
        """Add a visit to a plan and assert 201 with correct fields.

        Verifies that ``id``, ``plan_id``, ``customer_id``, ``customer_name``,
        ``scheduled_order``, and ``status`` are present with expected values.
        """
        rep_id = seed_users["rep"]["id"]
        customer_id = seed_customer["id"]
        customer_name = seed_customer["name"]

        plan = await _create_plan(client, rep_id)
        plan_id = plan["id"]

        resp = await client.post(
            f"/api/plans/{plan_id}/visits",
            json={
                "plan_id": plan_id,
                "customer_id": customer_id,
                "customer_name": customer_name,
                "scheduled_order": 1,
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "id" in body
        assert body["plan_id"] == plan_id
        assert body["customer_id"] == customer_id
        assert body["customer_name"] == customer_name
        assert body["scheduled_order"] == 1
        assert "status" in body

    @pytest.mark.anyio
    async def test_add_visit_missing_customer_id(self, client, seed_users, seed_customer):
        """Omit the customer_id field when adding a visit and assert 422."""
        rep_id = seed_users["rep"]["id"]
        customer_name = seed_customer["name"]

        plan = await _create_plan(client, rep_id)
        plan_id = plan["id"]

        resp = await client.post(
            f"/api/plans/{plan_id}/visits",
            json={
                "plan_id": plan_id,
                "customer_name": customer_name,
                "scheduled_order": 1,
            },
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_add_visit_missing_scheduled_order(self, client, seed_users, seed_customer):
        """Omit the scheduled_order field when adding a visit and assert 422."""
        rep_id = seed_users["rep"]["id"]
        customer_id = seed_customer["id"]
        customer_name = seed_customer["name"]

        plan = await _create_plan(client, rep_id)
        plan_id = plan["id"]

        resp = await client.post(
            f"/api/plans/{plan_id}/visits",
            json={
                "plan_id": plan_id,
                "customer_id": customer_id,
                "customer_name": customer_name,
            },
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_confirm_plan_no_visits(self, client, seed_users):
        """Confirm a plan that has no visits or calls and assert 422."""
        rep_id = seed_users["rep"]["id"]
        plan = await _create_plan(client, rep_id)

        resp = await client.patch(f"/api/plans/{plan['id']}/confirm")
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_confirm_plan_with_visit(self, client, seed_users, seed_customer):
        """Add a visit, confirm the plan, and assert 200 with status ``confirmed``."""
        rep_id = seed_users["rep"]["id"]
        customer_id = seed_customer["id"]
        customer_name = seed_customer["name"]

        plan = await _create_plan(client, rep_id)
        await _add_visit(client, plan["id"], customer_id, customer_name)

        resp = await client.patch(f"/api/plans/{plan['id']}/confirm")
        assert resp.status_code == 200
        assert resp.json()["status"] == "confirmed"

    @pytest.mark.anyio
    async def test_confirm_already_confirmed(self, client, seed_users, seed_customer):
        """Re-confirm an already confirmed plan and assert 409."""
        rep_id = seed_users["rep"]["id"]
        customer_id = seed_customer["id"]
        customer_name = seed_customer["name"]

        plan = await _create_plan(client, rep_id)
        await _add_visit(client, plan["id"], customer_id, customer_name)
        await _confirm_plan(client, plan["id"])

        resp = await client.patch(f"/api/plans/{plan['id']}/confirm")
        assert resp.status_code == 409

    @pytest.mark.anyio
    async def test_activate_confirmed_plan(self, client, seed_users, seed_customer):
        """Activate a confirmed plan and assert 200 with status ``active``."""
        rep_id = seed_users["rep"]["id"]
        customer_id = seed_customer["id"]
        customer_name = seed_customer["name"]

        plan = await _create_plan(client, rep_id)
        await _add_visit(client, plan["id"], customer_id, customer_name)
        await _confirm_plan(client, plan["id"])

        resp = await client.patch(f"/api/plans/{plan['id']}/activate")
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    @pytest.mark.anyio
    async def test_activate_draft_plan(self, client, seed_users):
        """Attempt to activate a draft plan and assert 409."""
        rep_id = seed_users["rep"]["id"]
        plan = await _create_plan(client, rep_id)

        resp = await client.patch(f"/api/plans/{plan['id']}/activate")
        assert resp.status_code == 409

    @pytest.mark.anyio
    async def test_complete_active_plan(self, client, seed_users, seed_customer):
        """Complete an active plan and assert 200 with status ``completed``."""
        rep_id = seed_users["rep"]["id"]
        customer_id = seed_customer["id"]
        customer_name = seed_customer["name"]

        plan = await _create_plan(client, rep_id)
        await _add_visit(client, plan["id"], customer_id, customer_name)
        await _confirm_plan(client, plan["id"])
        await _activate_plan(client, plan["id"])

        resp = await client.patch(f"/api/plans/{plan['id']}/complete")
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

    @pytest.mark.anyio
    async def test_complete_draft_plan(self, client, seed_users):
        """Attempt to complete a draft plan and assert 409."""
        rep_id = seed_users["rep"]["id"]
        plan = await _create_plan(client, rep_id)

        resp = await client.patch(f"/api/plans/{plan['id']}/complete")
        assert resp.status_code == 409

    @pytest.mark.anyio
    async def test_list_plans(self, client):
        """Fetch all plans and assert 200 with a list response body."""
        resp = await client.get("/api/plans")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.anyio
    async def test_get_plan_nonexistent(self, client):
        """Request a plan with a random UUID and assert 404."""
        resp = await client.get(f"/api/plans/{uuid.uuid4()}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Expense tests (14)
# ---------------------------------------------------------------------------

class TestExpenses:

    @pytest.mark.anyio
    async def test_create_expense_valid(self, client, seed_plan):
        """Create an expense with a valid payload and assert 201 with status ``submitted``.

        Verifies that ``id``, ``rep_id``, ``plan_id``, ``category``, ``amount``,
        and ``status`` are all present and have the expected values.
        """
        rep_id = seed_plan["plan"]["rep_id"]
        plan_id = seed_plan["plan"]["id"]

        resp = await client.post(
            "/api/expenses",
            json={
                "rep_id": rep_id,
                "plan_id": plan_id,
                "category": "fuel",
                "amount": "25.50",
                "description": "Motorway fuel",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "id" in body
        assert body["rep_id"] == rep_id
        assert body["plan_id"] == plan_id
        assert body["category"] == "fuel"
        assert body["status"] == "submitted"

    @pytest.mark.anyio
    async def test_create_expense_missing_rep_id(self, client, seed_plan):
        """Omit the rep_id field and assert the response is 422."""
        plan_id = seed_plan["plan"]["id"]

        resp = await client.post(
            "/api/expenses",
            json={
                "plan_id": plan_id,
                "category": "fuel",
                "amount": "25.50",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_create_expense_missing_plan_id(self, client, seed_users):
        """Omit the plan_id field and assert the response is 422."""
        rep_id = seed_users["rep"]["id"]

        resp = await client.post(
            "/api/expenses",
            json={
                "rep_id": rep_id,
                "category": "fuel",
                "amount": "25.50",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_create_expense_missing_category(self, client, seed_plan):
        """Omit the category field and assert the response is 422."""
        rep_id = seed_plan["plan"]["rep_id"]
        plan_id = seed_plan["plan"]["id"]

        resp = await client.post(
            "/api/expenses",
            json={
                "rep_id": rep_id,
                "plan_id": plan_id,
                "amount": "25.50",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_create_expense_missing_amount(self, client, seed_plan):
        """Omit the amount field and assert the response is 422."""
        rep_id = seed_plan["plan"]["rep_id"]
        plan_id = seed_plan["plan"]["id"]

        resp = await client.post(
            "/api/expenses",
            json={
                "rep_id": rep_id,
                "plan_id": plan_id,
                "category": "fuel",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_submit_expense(self, client, seed_plan):
        """Submit a draft expense and assert 200 with status ``pending_approval``."""
        rep_id = seed_plan["plan"]["rep_id"]
        plan_id = seed_plan["plan"]["id"]

        expense = await _create_expense(client, rep_id, plan_id)

        resp = await client.patch(f"/api/expenses/{expense['id']}/submit")
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending_approval"

    @pytest.mark.anyio
    async def test_submit_already_pending_expense(self, client, seed_plan):
        """Submit an already pending expense and assert 409."""
        rep_id = seed_plan["plan"]["rep_id"]
        plan_id = seed_plan["plan"]["id"]

        expense = await _create_expense(client, rep_id, plan_id)
        await _submit_expense(client, expense["id"])

        resp = await client.patch(f"/api/expenses/{expense['id']}/submit")
        assert resp.status_code == 409

    @pytest.mark.anyio
    async def test_approve_pending_expense(self, client, seed_users, seed_plan):
        """Approve a pending expense and assert 200 with status ``approved`` and non-null decided_at."""
        manager_id = seed_users["manager"]["id"]
        rep_id = seed_plan["plan"]["rep_id"]
        plan_id = seed_plan["plan"]["id"]

        expense = await _create_expense(client, rep_id, plan_id)
        await _submit_expense(client, expense["id"])

        resp = await client.patch(
            f"/api/expenses/{expense['id']}/approve",
            json={"manager_id": manager_id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "approved"
        assert body["decided_at"] is not None

    @pytest.mark.anyio
    async def test_approve_already_approved_expense(self, client, seed_users, seed_plan):
        """Re-approve an already approved expense and assert 409."""
        manager_id = seed_users["manager"]["id"]
        rep_id = seed_plan["plan"]["rep_id"]
        plan_id = seed_plan["plan"]["id"]

        expense = await _create_expense(client, rep_id, plan_id)
        await _submit_expense(client, expense["id"])
        await _approve_expense(client, expense["id"], manager_id)

        resp = await client.patch(
            f"/api/expenses/{expense['id']}/approve",
            json={"manager_id": manager_id},
        )
        assert resp.status_code == 409

    @pytest.mark.anyio
    async def test_reject_pending_expense(self, client, seed_users, seed_plan):
        """Reject a pending expense and assert 200 with status ``rejected``."""
        manager_id = seed_users["manager"]["id"]
        rep_id = seed_plan["plan"]["rep_id"]
        plan_id = seed_plan["plan"]["id"]

        expense = await _create_expense(client, rep_id, plan_id)
        await _submit_expense(client, expense["id"])

        resp = await client.patch(
            f"/api/expenses/{expense['id']}/reject",
            json={"manager_id": manager_id},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

    @pytest.mark.anyio
    async def test_resubmit_rejected_expense(self, client, seed_users, seed_plan):
        """Resubmit a rejected expense and assert 200 with status ``submitted``."""
        manager_id = seed_users["manager"]["id"]
        rep_id = seed_plan["plan"]["rep_id"]
        plan_id = seed_plan["plan"]["id"]

        expense = await _create_expense(client, rep_id, plan_id)
        await _submit_expense(client, expense["id"])
        await _reject_expense(client, expense["id"], manager_id)

        resp = await client.patch(
            f"/api/expenses/{expense['id']}/resubmit",
            json={},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "submitted"

    @pytest.mark.anyio
    async def test_resubmit_approved_expense(self, client, seed_users, seed_plan):
        """Attempt to resubmit an approved expense and assert 409."""
        manager_id = seed_users["manager"]["id"]
        rep_id = seed_plan["plan"]["rep_id"]
        plan_id = seed_plan["plan"]["id"]

        expense = await _create_expense(client, rep_id, plan_id)
        await _submit_expense(client, expense["id"])
        await _approve_expense(client, expense["id"], manager_id)

        resp = await client.patch(
            f"/api/expenses/{expense['id']}/resubmit",
            json={},
        )
        assert resp.status_code == 409

    @pytest.mark.anyio
    async def test_list_expenses(self, client):
        """Fetch all expenses and assert 200 with a list response body."""
        resp = await client.get("/api/expenses")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.anyio
    async def test_get_expense_nonexistent(self, client):
        """Request an expense with a random UUID and assert 404."""
        resp = await client.get(f"/api/expenses/{uuid.uuid4()}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# CQRS tests (8)
# ---------------------------------------------------------------------------

class TestCQRS:

    @pytest.mark.anyio
    async def test_plan_history_after_create(self, client, seed_users):
        """Creating a plan adds a row with status ``draft`` and zero counts to the history.

        Verifies that ``status`` is ``"draft"``, ``visit_count`` is 0, and
        ``call_count`` is 0 immediately after plan creation.
        """
        rep_id = seed_users["rep"]["id"]
        plan = await _create_plan(client, rep_id)

        resp = await client.get(
            "/api/plans/read/history", params={"rep_id": rep_id}
        )
        assert resp.status_code == 200
        row = _find_by_id(resp.json(), plan["id"])
        assert row is not None
        assert row["rep_id"] == rep_id
        assert row["status"] == "draft"
        assert row["visit_count"] == 0
        assert row["call_count"] == 0

    @pytest.mark.anyio
    async def test_plan_history_visit_count(self, client, seed_users, seed_customer):
        """Adding a visit to a plan increments visit_count to 1 in the history."""
        rep_id = seed_users["rep"]["id"]
        customer_id = seed_customer["id"]
        customer_name = seed_customer["name"]

        plan = await _create_plan(client, rep_id)
        await _add_visit(client, plan["id"], customer_id, customer_name)

        resp = await client.get(
            "/api/plans/read/history", params={"rep_id": rep_id}
        )
        assert resp.status_code == 200
        row = _find_by_id(resp.json(), plan["id"])
        assert row is not None
        assert row["visit_count"] == 1

    @pytest.mark.anyio
    async def test_plan_history_after_confirm(self, client, seed_users, seed_customer):
        """Confirming a plan updates its status to ``confirmed`` in the history."""
        rep_id = seed_users["rep"]["id"]
        customer_id = seed_customer["id"]
        customer_name = seed_customer["name"]

        plan = await _create_plan(client, rep_id)
        await _add_visit(client, plan["id"], customer_id, customer_name)
        await _confirm_plan(client, plan["id"])

        resp = await client.get(
            "/api/plans/read/history", params={"rep_id": rep_id}
        )
        assert resp.status_code == 200
        row = _find_by_id(resp.json(), plan["id"])
        assert row is not None
        assert row["status"] == "confirmed"

    @pytest.mark.anyio
    async def test_plan_read_rep(self, client, seed_users):
        """GET /api/plans/read/rep/{rep_id} returns only plans for that rep.

        Creates a plan for the seeded rep and asserts that every row in the
        response belongs to the same rep_id.
        """
        rep_id = seed_users["rep"]["id"]
        await _create_plan(client, rep_id)

        resp = await client.get(f"/api/plans/read/rep/{rep_id}")
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) >= 1
        assert all(r["rep_id"] == rep_id for r in rows)

    @pytest.mark.anyio
    async def test_plan_read_active(self, client, seed_users, seed_customer):
        """Activating a plan causes it to appear in GET /api/plans/read/active.

        Creates a plan, adds a visit, confirms it, activates it, then asserts
        the plan is present in the active-plans read endpoint with status
        ``"active"``.
        """
        rep_id = seed_users["rep"]["id"]
        customer_id = seed_customer["id"]
        customer_name = seed_customer["name"]

        plan = await _create_plan(client, rep_id)
        await _add_visit(client, plan["id"], customer_id, customer_name)
        await _confirm_plan(client, plan["id"])
        await _activate_plan(client, plan["id"])

        resp = await client.get("/api/plans/read/active")
        assert resp.status_code == 200
        rows = resp.json()
        row = _find_by_id(rows, plan["id"])
        assert row is not None
        assert row["status"] == "active"

    @pytest.mark.anyio
    async def test_expense_history_after_create(self, client, seed_users):
        """Creating an expense adds a row with status ``submitted`` to the history."""
        rep_id = seed_users["rep"]["id"]
        plan = await _create_plan(client, rep_id)
        expense = await _create_expense(client, rep_id, plan["id"])

        resp = await client.get(
            "/api/expenses/read/history", params={"rep_id": rep_id}
        )
        assert resp.status_code == 200
        row = _find_by_id(resp.json(), expense["id"])
        assert row is not None
        assert row["status"] == "submitted"

    @pytest.mark.anyio
    async def test_expense_history_after_approve(self, client, seed_users):
        """Approving an expense updates status to ``approved`` and sets decided_at.

        Creates an expense, submits it, approves it, then asserts that the
        history row reflects ``"approved"`` status and a non-null ``decided_at``.
        """
        rep_id = seed_users["rep"]["id"]
        manager_id = seed_users["manager"]["id"]
        plan = await _create_plan(client, rep_id)
        expense = await _create_expense(client, rep_id, plan["id"])
        await _submit_expense(client, expense["id"])
        await _approve_expense(client, expense["id"], manager_id)

        resp = await client.get(
            "/api/expenses/read/history", params={"rep_id": rep_id}
        )
        assert resp.status_code == 200
        row = _find_by_id(resp.json(), expense["id"])
        assert row is not None
        assert row["status"] == "approved"
        assert row["decided_at"] is not None

    @pytest.mark.anyio
    async def test_expense_read_rep(self, client, seed_users):
        """GET /api/expenses/read/rep/{rep_id} returns only expenses for that rep.

        Creates an expense for the seeded rep and asserts that every row in the
        response belongs to the same rep_id.
        """
        rep_id = seed_users["rep"]["id"]
        plan = await _create_plan(client, rep_id)
        await _create_expense(client, rep_id, plan["id"])

        resp = await client.get(f"/api/expenses/read/rep/{rep_id}")
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) >= 1
        assert all(r["rep_id"] == rep_id for r in rows)


# ---------------------------------------------------------------------------
# Edge case tests (13)
# ---------------------------------------------------------------------------

class TestEdgeCases:

    @pytest.mark.anyio
    async def test_list_plans_empty_for_unknown_rep(self, client):
        """GET /api/plans filtered by an unknown rep UUID returns 200 and an empty list."""
        resp = await client.get("/api/plans", params={"rep_id": str(uuid.uuid4())})
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.anyio
    async def test_list_expenses_empty_for_unknown_rep(self, client):
        """GET /api/expenses filtered by an unknown rep UUID returns 200 and an empty list."""
        resp = await client.get(
            "/api/expenses", params={"rep_id": str(uuid.uuid4())}
        )
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.anyio
    async def test_plan_history_empty_for_unknown_rep(self, client):
        """GET /api/plans/read/history for an unknown rep_id returns 200 and an empty list."""
        resp = await client.get(
            "/api/plans/read/history", params={"rep_id": str(uuid.uuid4())}
        )
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.anyio
    async def test_expense_history_empty_for_unknown_rep(self, client):
        """GET /api/expenses/read/history for an unknown rep_id returns 200 and an empty list."""
        resp = await client.get(
            "/api/expenses/read/history", params={"rep_id": str(uuid.uuid4())}
        )
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.anyio
    async def test_get_plan_not_found(self, client):
        """GET /api/plans/{id} with a random UUID returns 404."""
        resp = await client.get(f"/api/plans/{uuid.uuid4()}")
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_get_expense_not_found(self, client):
        """GET /api/expenses/{id} with a random UUID returns 404."""
        resp = await client.get(f"/api/expenses/{uuid.uuid4()}")
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_get_user_not_found(self, client):
        """GET /api/users/{id} with a random UUID returns 404."""
        resp = await client.get(f"/api/users/{uuid.uuid4()}")
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_get_customer_not_found(self, client):
        """GET /api/customers/{id} with a random UUID returns 404."""
        resp = await client.get(f"/api/customers/{uuid.uuid4()}")
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_create_plan_empty_body(self, client):
        """POST /api/plans with an empty body returns 422."""
        resp = await client.post("/api/plans", json={})
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_create_expense_empty_body(self, client):
        """POST /api/expenses with an empty body returns 422."""
        resp = await client.post("/api/expenses", json={})
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_create_user_empty_body(self, client):
        """POST /api/users with an empty body returns 422."""
        resp = await client.post("/api/users", json={})
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_create_customer_empty_body(self, client):
        """POST /api/customers with an empty body returns 422."""
        resp = await client.post("/api/customers", json={})
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_add_visit_unknown_plan(self, client):
        """POST /api/plans/{id}/visits with a random plan UUID returns 404."""
        plan_id = str(uuid.uuid4())
        resp = await client.post(
            f"/api/plans/{plan_id}/visits",
            json={
                "plan_id": plan_id,
                "customer_id": str(uuid.uuid4()),
                "customer_name": "Ghost Customer",
                "scheduled_order": 1,
            },
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Saga tests (4)
# ---------------------------------------------------------------------------

class TestSaga:

    @pytest.mark.anyio
    async def test_deactivate_customer_no_active_plans(self, client):
        """Deactivate a customer who has no plans and assert 200 with is_active False.

        Verifies that the endpoint responds correctly when there is nothing
        for the planning service consumer to roll back.
        """
        customer = await _create_customer(client)

        resp = await client.patch(f"/api/customers/{customer['id']}/deactivate")
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    @pytest.mark.anyio
    async def test_deactivate_customer_confirmed_plan_rolls_back(self, client):
        """Deactivating a customer whose plan is confirmed rolls the plan back to ``draft``.

        Creates a rep, a customer, a plan, adds a visit for that customer,
        confirms the plan, then deactivates the customer.  Polls the plan
        endpoint for up to 20 seconds and asserts the status reverts to
        ``"draft"`` via the Kafka-driven saga.
        """
        rep = await _create_user(client, "sales_rep")
        customer = await _create_customer(client)

        plan = await _create_plan(client, rep["id"])
        await _add_visit(client, plan["id"], customer["id"], customer["name"])
        await _confirm_plan(client, plan["id"])

        await _deactivate_customer(client, customer["id"])

        final_status = await _poll_plan_status(client, plan["id"], "draft")
        assert final_status == "draft"

    @pytest.mark.anyio
    async def test_deactivate_customer_active_plan_rolls_back(self, client):
        """Deactivating a customer whose plan is active rolls the plan back to ``draft``.

        Creates a rep, a customer, a plan, adds a visit, confirms then
        activates the plan, then deactivates the customer.  Polls the plan
        endpoint for up to 20 seconds and asserts the status reverts to
        ``"draft"`` via the Kafka-driven saga.
        """
        rep = await _create_user(client, "sales_rep")
        customer = await _create_customer(client)

        plan = await _create_plan(client, rep["id"])
        await _add_visit(client, plan["id"], customer["id"], customer["name"])
        await _confirm_plan(client, plan["id"])
        await _activate_plan(client, plan["id"])

        await _deactivate_customer(client, customer["id"])

        final_status = await _poll_plan_status(client, plan["id"], "draft")
        assert final_status == "draft"

    @pytest.mark.anyio
    async def test_deactivate_already_inactive_customer(self, client):
        """Deactivating an already inactive customer returns 409."""
        customer = await _create_customer(client)
        await _deactivate_customer(client, customer["id"])

        resp = await client.patch(f"/api/customers/{customer['id']}/deactivate")
        assert resp.status_code == 409
