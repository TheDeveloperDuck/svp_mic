"""Integration tests for the customer-deactivation saga.

Tests verify the end-to-end flow triggered when a customer is deactivated:

1. The Customer User Service soft-deletes the customer and publishes a
   ``customer.deactivated`` Kafka event.
2. The Planning Service consumer receives the event and rolls any
   ``confirmed`` or ``active`` plans that reference the customer back to
   ``draft``.

All tests create their own users, customers, and plans so that the
destructive deactivation cannot affect other tests or be undone between
runs.

Endpoints under test:
- PATCH  /api/customers/{customer_id}/deactivate  -- soft-delete a customer.
- GET    /api/plans/{plan_id}                     -- poll the rolled-back plan.

Test cases:
- test_deactivate_customer_no_active_plans -- deactivating a customer with no
  plans returns 200 with is_active False.
- test_deactivate_customer_confirmed_plan_rolls_back -- deactivating a customer
  whose plan is confirmed causes the plan to revert to "draft" within 5 s.
- test_deactivate_customer_active_plan_rolls_back -- deactivating a customer
  whose plan is active causes the plan to revert to "draft" within 5 s.
- test_deactivate_already_inactive_customer -- deactivating an already
  inactive customer returns 409.
"""

import asyncio
import secrets


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
) -> dict:
    """Add a visit referencing the given customer to a plan.

    Arguments:
    client        -- active httpx.AsyncClient.
    plan_id       -- UUID string of the parent plan.
    customer_id   -- UUID string of the customer to visit.
    customer_name -- display name of the customer.

    Return value:
    dict -- full JSON response body of the created visit.
    """
    resp = await client.post(
        f"/api/plans/{plan_id}/visits",
        json={
            "plan_id": plan_id,
            "customer_id": customer_id,
            "customer_name": customer_name,
            "scheduled_order": 1,
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
    dict -- full JSON response body of the confirmed plan.
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
    dict -- full JSON response body of the activated plan.
    """
    resp = await client.patch(f"/api/plans/{plan_id}/activate")
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
    attempts: int = 10,
    interval: float = 0.5,
) -> str:
    """Poll GET /api/plans/{plan_id} until the status matches or attempts run out.

    Arguments:
    client        -- active httpx.AsyncClient.
    plan_id       -- UUID string of the plan to poll.
    target_status -- status value to wait for.
    attempts      -- maximum number of polling attempts (default 10).
    interval      -- seconds to wait between attempts (default 0.5).

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


# ---------------------------------------------------------------------------
# Deactivation: no active plans
# ---------------------------------------------------------------------------

async def test_deactivate_customer_no_active_plans(client):
    """Deactivate a customer who has no plans and assert 200 with is_active False.

    Verifies that the endpoint responds correctly when there is nothing
    for the planning service consumer to roll back.
    """
    customer = await _create_customer(client)

    resp = await client.patch(f"/api/customers/{customer['id']}/deactivate")
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


# ---------------------------------------------------------------------------
# Deactivation: confirmed plan rolls back
# ---------------------------------------------------------------------------

async def test_deactivate_customer_confirmed_plan_rolls_back(client):
    """Deactivating a customer whose plan is confirmed rolls the plan back to ``draft``.

    Creates a rep, a customer, a plan, adds a visit for that customer,
    confirms the plan, then deactivates the customer.  Polls the plan
    endpoint for up to 5 seconds and asserts the status reverts to
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


# ---------------------------------------------------------------------------
# Deactivation: active plan rolls back
# ---------------------------------------------------------------------------

async def test_deactivate_customer_active_plan_rolls_back(client):
    """Deactivating a customer whose plan is active rolls the plan back to ``draft``.

    Creates a rep, a customer, a plan, adds a visit, confirms then
    activates the plan, then deactivates the customer.  Polls the plan
    endpoint for up to 5 seconds and asserts the status reverts to
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


# ---------------------------------------------------------------------------
# Deactivation: already inactive
# ---------------------------------------------------------------------------

async def test_deactivate_already_inactive_customer(client):
    """Deactivating an already inactive customer returns 409."""
    customer = await _create_customer(client)
    await _deactivate_customer(client, customer["id"])

    resp = await client.patch(f"/api/customers/{customer['id']}/deactivate")
    assert resp.status_code == 409
