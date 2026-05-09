"""Integration tests for the Plans endpoints of the Planning Service.

Tests hit the running Docker stack at http://localhost via nginx.
No service code is imported; all interaction is over HTTP.

Endpoints under test:
- POST   /api/plans                          -- create a new day plan.
- GET    /api/plans                          -- list all plans.
- GET    /api/plans/{plan_id}                -- fetch a single plan.
- PATCH  /api/plans/{plan_id}/confirm        -- confirm a draft plan.
- PATCH  /api/plans/{plan_id}/activate       -- activate a confirmed plan.
- PATCH  /api/plans/{plan_id}/complete       -- complete an active plan.
- POST   /api/plans/{plan_id}/visits         -- add a visit to a plan.

Test cases:
- test_create_plan_valid -- valid rep_id returns 201 with status "draft".
- test_create_plan_nonexistent_rep_id -- unknown rep UUID returns 404 or 422.
- test_create_plan_missing_date -- absent date field returns 422.
- test_create_plan_missing_start_location -- absent start_location returns 422.
- test_create_plan_missing_end_location -- absent end_location returns 422.
- test_add_visit -- adding a visit returns 201 with correct fields.
- test_add_visit_missing_customer_id -- absent customer_id returns 422.
- test_add_visit_missing_scheduled_order -- absent scheduled_order returns 422.
- test_confirm_plan_no_visits -- confirming a plan without visits returns 422.
- test_confirm_plan_with_visit -- confirming after a visit returns 200 with status "confirmed".
- test_confirm_already_confirmed -- re-confirming a confirmed plan returns 409.
- test_activate_confirmed_plan -- activating a confirmed plan returns 200 with status "active".
- test_activate_draft_plan -- activating a draft plan returns 409.
- test_complete_active_plan -- completing an active plan returns 200 with status "completed".
- test_complete_draft_plan -- completing a draft plan returns 409.
- test_list_plans -- GET /api/plans returns 200 with a list body.
- test_get_plan_nonexistent -- unknown plan UUID returns 404.
"""

import uuid


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
        json={"rep_id": rep_id, "date": "2026-04-15", "start_location": "Dublin", "end_location": "Cork"},
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


# ---------------------------------------------------------------------------
# Create plan
# ---------------------------------------------------------------------------

async def test_create_plan_valid(client, seed_users):
    """Create a plan with a valid rep_id and assert 201 with status ``draft``.

    Verifies that ``id``, ``rep_id``, ``date``, and ``status`` are all
    present and have the expected values.
    """
    rep_id = seed_users["rep"]["id"]
    resp = await client.post(
        "/api/plans",
        json={"rep_id": rep_id, "date": "2026-04-15", "start_location": "Dublin", "end_location": "Cork"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body
    assert body["rep_id"] == rep_id
    assert body["date"] == "2026-04-15"
    assert body["status"] == "draft"


async def test_create_plan_nonexistent_rep_id(client):
    """Submit a random rep UUID and assert the response is 404 or 422."""
    resp = await client.post(
        "/api/plans",
        json={"rep_id": str(uuid.uuid4()), "date": "2026-04-15"},
    )
    assert resp.status_code in (404, 422)


async def test_create_plan_missing_date(client, seed_users):
    """Omit the date field and assert the response is 422."""
    rep_id = seed_users["rep"]["id"]
    resp = await client.post(
        "/api/plans",
        json={"rep_id": rep_id},
    )
    assert resp.status_code == 422


async def test_create_plan_missing_start_location(client, seed_users):
    """Omit the start_location field and assert the response is 422."""
    rep_id = seed_users["rep"]["id"]
    resp = await client.post(
        "/api/plans",
        json={"rep_id": rep_id, "date": "2026-04-15", "end_location": "Cork"},
    )
    assert resp.status_code == 422


async def test_create_plan_missing_end_location(client, seed_users):
    """Omit the end_location field and assert the response is 422."""
    rep_id = seed_users["rep"]["id"]
    resp = await client.post(
        "/api/plans",
        json={"rep_id": rep_id, "date": "2026-04-15", "start_location": "Dublin"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Add visit
# ---------------------------------------------------------------------------

async def test_add_visit(client, seed_users, seed_customer):
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


async def test_add_visit_missing_customer_id(client, seed_users, seed_customer):
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


async def test_add_visit_missing_scheduled_order(
    client, seed_users, seed_customer
):
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


# ---------------------------------------------------------------------------
# Confirm plan
# ---------------------------------------------------------------------------

async def test_confirm_plan_no_visits(client, seed_users):
    """Confirm a plan that has no visits or calls and assert 422."""
    rep_id = seed_users["rep"]["id"]
    plan = await _create_plan(client, rep_id)

    resp = await client.patch(f"/api/plans/{plan['id']}/confirm")
    assert resp.status_code == 422


async def test_confirm_plan_with_visit(client, seed_users, seed_customer):
    """Add a visit, confirm the plan, and assert 200 with status ``confirmed``."""
    rep_id = seed_users["rep"]["id"]
    customer_id = seed_customer["id"]
    customer_name = seed_customer["name"]

    plan = await _create_plan(client, rep_id)
    await _add_visit(client, plan["id"], customer_id, customer_name)

    resp = await client.patch(f"/api/plans/{plan['id']}/confirm")
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed"


async def test_confirm_already_confirmed(client, seed_users, seed_customer):
    """Re-confirm an already confirmed plan and assert 409."""
    rep_id = seed_users["rep"]["id"]
    customer_id = seed_customer["id"]
    customer_name = seed_customer["name"]

    plan = await _create_plan(client, rep_id)
    await _add_visit(client, plan["id"], customer_id, customer_name)
    await _confirm_plan(client, plan["id"])

    resp = await client.patch(f"/api/plans/{plan['id']}/confirm")
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Activate plan
# ---------------------------------------------------------------------------

async def test_activate_confirmed_plan(client, seed_users, seed_customer):
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


async def test_activate_draft_plan(client, seed_users):
    """Attempt to activate a draft plan and assert 409."""
    rep_id = seed_users["rep"]["id"]
    plan = await _create_plan(client, rep_id)

    resp = await client.patch(f"/api/plans/{plan['id']}/activate")
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Complete plan
# ---------------------------------------------------------------------------

async def test_complete_active_plan(client, seed_users, seed_customer):
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


async def test_complete_draft_plan(client, seed_users):
    """Attempt to complete a draft plan and assert 409."""
    rep_id = seed_users["rep"]["id"]
    plan = await _create_plan(client, rep_id)

    resp = await client.patch(f"/api/plans/{plan['id']}/complete")
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# List and fetch
# ---------------------------------------------------------------------------

async def test_list_plans(client):
    """Fetch all plans and assert 200 with a list response body."""
    resp = await client.get("/api/plans")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_get_plan_nonexistent(client):
    """Request a plan with a random UUID and assert 404."""
    resp = await client.get(f"/api/plans/{uuid.uuid4()}")
    assert resp.status_code == 404
