import asyncio
import secrets
import statistics
import time

import httpx
import pytest

from tests.stress.conftest import make_client, create_user, create_customer


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _create_plan(client: httpx.AsyncClient, rep_id: str, suffix: str) -> dict:
    resp = await client.post("/api/plans", json={
        "rep_id": rep_id,
        "date": "2025-06-01",
        "start_location": f"Start {suffix}",
        "end_location": f"End {suffix}",
    })
    resp.raise_for_status()
    return resp.json()


async def _add_visit(
    client: httpx.AsyncClient,
    plan_id: str,
    customer_id: str,
    customer_name: str,
    order: int = 1,
) -> dict:
    resp = await client.post(f"/api/plans/{plan_id}/visits", json={
        "plan_id": plan_id,
        "customer_id": customer_id,
        "customer_name": customer_name,
        "scheduled_order": order,
    })
    resp.raise_for_status()
    return resp.json()


async def _confirm_plan(client: httpx.AsyncClient, plan_id: str) -> httpx.Response:
    return await client.patch(f"/api/plans/{plan_id}/confirm")


async def _activate_plan(client: httpx.AsyncClient, plan_id: str) -> httpx.Response:
    return await client.patch(f"/api/plans/{plan_id}/activate")


async def _complete_plan(client: httpx.AsyncClient, plan_id: str) -> httpx.Response:
    return await client.patch(f"/api/plans/{plan_id}/complete")


async def _deactivate_customer(client: httpx.AsyncClient, customer_id: str) -> httpx.Response:
    return await client.patch(f"/api/customers/{customer_id}/deactivate")


async def _create_expense(
    client: httpx.AsyncClient, rep_id: str, plan_id: str, suffix: str
) -> dict:
    resp = await client.post("/api/expenses", json={
        "rep_id": rep_id,
        "plan_id": plan_id,
        "category": "fuel",
        "amount": 25.50,
        "description": f"Expense {suffix}",
    })
    resp.raise_for_status()
    return resp.json()


async def _submit_expense(client: httpx.AsyncClient, expense_id: str) -> httpx.Response:
    return await client.patch(f"/api/expenses/{expense_id}/submit")


async def _approve_expense(
    client: httpx.AsyncClient, expense_id: str, manager_id: str
) -> httpx.Response:
    return await client.patch(
        f"/api/expenses/{expense_id}/approve",
        json={"manager_id": manager_id},
    )


async def _poll_plan_status(
    client: httpx.AsyncClient,
    plan_id: str,
    target: str,
    attempts: int,
    interval: float,
) -> str:
    for _ in range(attempts):
        resp = await client.get(f"/api/plans/{plan_id}")
        if resp.status_code == 200:
            status = resp.json().get("status")
            if status == target:
                return status
        await asyncio.sleep(interval)
    resp = await client.get(f"/api/plans/{plan_id}")
    return resp.json().get("status", "unknown")


# ---------------------------------------------------------------------------
# Mixed reads and writes
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@pytest.mark.stress
async def test_50_concurrent_writes_50_concurrent_reads_simultaneously():
    suffixes = [secrets.token_hex(4) for _ in range(50)]
    write_bodies = [
        {"name": f"Customer {s}", "address": f"Address {s}"}
        for s in suffixes
    ]

    start = time.monotonic()
    async with make_client() as client:
        async def _write(body: dict) -> int:
            try:
                resp = await client.post("/api/customers", json=body)
                return resp.status_code
            except Exception:
                return 0

        async def _read() -> tuple[int, object]:
            try:
                resp = await client.get("/api/customers")
                return resp.status_code, resp.json()
            except Exception:
                return 0, None

        write_tasks = [_write(b) for b in write_bodies]
        read_tasks = [_read() for _ in range(50)]

        results = await asyncio.gather(*write_tasks, *read_tasks)

    elapsed = time.monotonic() - start
    write_codes = list(results[:50])
    read_results = list(results[50:])

    read_codes = [code for code, _ in read_results]
    read_bodies_list = [body for _, body in read_results]

    write_5xx = [c for c in write_codes if 500 <= c <= 599]
    read_5xx = [c for c in read_codes if 500 <= c <= 599]

    print(
        f"\n[50w+50r] {elapsed:.2f}s write_codes={sorted(set(write_codes))} "
        f"read_codes={sorted(set(read_codes))}"
    )

    assert len(write_5xx) == 0, f"Got {len(write_5xx)} 5xx on writes"
    assert len(read_5xx) == 0, f"Got {len(read_5xx)} 5xx on reads"

    for i, body in enumerate(read_bodies_list):
        assert isinstance(body, list), (
            f"Read {i} returned non-list body: {type(body)}"
        )


# ---------------------------------------------------------------------------
# Saga under load — 10 concurrent triggers
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@pytest.mark.stress
async def test_10_concurrent_saga_triggers():
    suffix = secrets.token_hex(4)
    start = time.monotonic()

    async with make_client() as client:
        rep = await create_user(client, suffix)
        rep_id = rep["id"]

        async def _setup(i: int) -> tuple[str, str]:
            s = secrets.token_hex(4)
            customer = await create_customer(client, s)
            plan = await _create_plan(client, rep_id, s)
            await _add_visit(client, plan["id"], customer["id"], customer["name"])
            await _confirm_plan(client, plan["id"])
            return customer["id"], plan["id"]

        setups = await asyncio.gather(*[_setup(i) for i in range(10)])
        customer_ids = [c for c, _ in setups]
        plan_ids = [p for _, p in setups]

        await asyncio.gather(*[_deactivate_customer(client, cid) for cid in customer_ids])

        # Poll up to 15 seconds for all plans to revert to draft
        for _ in range(15):
            await asyncio.sleep(1)
            resps = await asyncio.gather(*[client.get(f"/api/plans/{pid}") for pid in plan_ids])
            statuses = [r.json()["status"] for r in resps]
            if all(s == "draft" for s in statuses):
                break

        resps = await asyncio.gather(*[client.get(f"/api/plans/{pid}") for pid in plan_ids])
        final_statuses = [r.json()["status"] for r in resps]

    elapsed = time.monotonic() - start
    not_draft = [(plan_ids[i], final_statuses[i]) for i in range(10) if final_statuses[i] != "draft"]
    print(
        f"\n[saga x10] {elapsed:.2f}s final_statuses={final_statuses} "
        f"not_draft={len(not_draft)}"
    )

    assert len(not_draft) == 0, (
        f"Plans did not revert to draft within 15s: {not_draft}"
    )


# ---------------------------------------------------------------------------
# Saga under load — 50 concurrent triggers (degraded threshold)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@pytest.mark.stress
async def test_50_concurrent_saga_triggers():
    # allow cluster to stabilise after previous heavy test
    await asyncio.sleep(5)
    suffix = secrets.token_hex(4)
    start = time.monotonic()

    async with make_client() as client:
        rep = await create_user(client, suffix)
        rep_id = rep["id"]

        async def _setup(i: int) -> tuple[str, str]:
            s = secrets.token_hex(4)
            customer = await create_customer(client, s)
            plan = await _create_plan(client, rep_id, s)
            await _add_visit(client, plan["id"], customer["id"], customer["name"])
            await _confirm_plan(client, plan["id"])
            return customer["id"], plan["id"]

        setups = await asyncio.gather(*[_setup(i) for i in range(50)])
        customer_ids = [c for c, _ in setups]
        plan_ids = [p for _, p in setups]

        await asyncio.gather(*[_deactivate_customer(client, cid) for cid in customer_ids])

        reverted_at_10s = 0
        reverted_at_20s = 0
        reverted_at_30s = 0

        for tick in range(30):
            await asyncio.sleep(1)
            resps = await asyncio.gather(*[client.get(f"/api/plans/{pid}") for pid in plan_ids])
            statuses = [r.json()["status"] for r in resps]
            drafted = sum(1 for s in statuses if s == "draft")

            if tick == 9:
                reverted_at_10s = drafted
            if tick == 19:
                reverted_at_20s = drafted
            if tick == 29:
                reverted_at_30s = drafted

            if drafted == 50:
                break

        resps = await asyncio.gather(*[client.get(f"/api/plans/{pid}") for pid in plan_ids])
        final_statuses = [r.json()["status"] for r in resps]

    elapsed = time.monotonic() - start
    reverted_final = sum(1 for s in final_statuses if s == "draft")

    print(
        f"\n[saga x50] {elapsed:.2f}s "
        f"reverted_at_10s={reverted_at_10s}/50 "
        f"reverted_at_20s={reverted_at_20s}/50 "
        f"reverted_at_30s={reverted_at_30s}/50 "
        f"final={reverted_final}/50"
    )

    assert reverted_final >= 40, (
        f"Less than 80% (40/50) plans reverted to draft within 30s: {reverted_final}/50"
    )
    stuck_confirmed = [
        plan_ids[i] for i in range(50) if final_statuses[i] == "confirmed"
    ]
    assert len(stuck_confirmed) < 50, (
        "All plans permanently stuck in confirmed — Kafka consumer appears stalled"
    )


# ---------------------------------------------------------------------------
# 20 concurrent deactivations of active plans
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@pytest.mark.stress
async def test_20_concurrent_customer_deactivations_active_plans():
    suffix = secrets.token_hex(4)
    start = time.monotonic()

    async with make_client() as client:
        rep = await create_user(client, suffix)
        rep_id = rep["id"]

        async def _setup(i: int) -> tuple[str, str]:
            s = secrets.token_hex(4)
            customer = await create_customer(client, s)
            plan = await _create_plan(client, rep_id, s)
            await _add_visit(client, plan["id"], customer["id"], customer["name"])
            await _confirm_plan(client, plan["id"])
            await _activate_plan(client, plan["id"])
            return customer["id"], plan["id"]

        setups = await asyncio.gather(*[_setup(i) for i in range(20)])
        customer_ids = [c for c, _ in setups]
        plan_ids = [p for _, p in setups]

        await asyncio.gather(*[_deactivate_customer(client, cid) for cid in customer_ids])

        for _ in range(20):
            await asyncio.sleep(1)
            resps = await asyncio.gather(*[client.get(f"/api/plans/{pid}") for pid in plan_ids])
            statuses = [r.json()["status"] for r in resps]
            if all(s == "draft" for s in statuses):
                break

        resps = await asyncio.gather(*[client.get(f"/api/plans/{pid}") for pid in plan_ids])
        final_statuses = [r.json()["status"] for r in resps]

    elapsed = time.monotonic() - start
    not_draft = [(plan_ids[i], final_statuses[i]) for i in range(20) if final_statuses[i] != "draft"]
    print(
        f"\n[saga active x20] {elapsed:.2f}s not_draft={len(not_draft)}"
    )

    assert len(not_draft) == 0, (
        f"Active plans did not revert to draft within 20s: {not_draft}"
    )


# ---------------------------------------------------------------------------
# Outbox poller pressure — 100 concurrent plan confirmations
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@pytest.mark.stress
async def test_100_concurrent_plan_confirmations():
    suffix = secrets.token_hex(4)
    start = time.monotonic()

    async with make_client() as client:
        rep = await create_user(client, suffix)
        rep_id = rep["id"]
        customer = await create_customer(client, suffix)
        customer_id = customer["id"]
        customer_name = customer["name"]

        # Create 100 draft plans each with one visit
        plans = await asyncio.gather(*[
            _create_plan(client, rep_id, secrets.token_hex(4))
            for _ in range(100)
        ])

        await asyncio.gather(*[
            _add_visit(client, p["id"], customer_id, customer_name)
            for p in plans
        ])

        confirm_resps = await asyncio.gather(*[
            _confirm_plan(client, p["id"])
            for p in plans
        ])

    confirm_codes = [r.status_code for r in confirm_resps]
    confirm_bodies = [r.json() for r in confirm_resps]
    five_xx = [c for c in confirm_codes if 500 <= c <= 599]
    not_200 = [c for c in confirm_codes if c != 200]

    print(
        f"\n[100 confirmations] setup+confirm elapsed so far "
        f"5xx={len(five_xx)} not_200={len(not_200)}"
    )

    assert len(five_xx) == 0, f"Got {len(five_xx)} 5xx on confirm"
    assert len(not_200) == 0, f"Got {len(not_200)} non-200 on confirm: {sorted(set(not_200))}"
    for body in confirm_bodies:
        assert body.get("status") == "confirmed", (
            f"Plan not in confirmed state after confirm: {body.get('status')}"
        )

    # Poll read model for all 100 to appear
    plan_ids = {p["id"] for p in plans}
    async with make_client() as client:
        for _ in range(15):
            await asyncio.sleep(1)
            resp = await client.get("/api/plans/read/history", params={"rep_id": rep_id})
            if resp.status_code == 200:
                rows = resp.json()
                matched_ids = {r["id"] for r in rows if r["id"] in plan_ids}
                if len(matched_ids) == 100:
                    break

        resp = await client.get("/api/plans/read/history", params={"rep_id": rep_id})
        rows = resp.json()

    elapsed = time.monotonic() - start
    matched_ids = {r["id"] for r in rows if r["id"] in plan_ids}
    print(
        f"\n[100 confirmations] total_time={elapsed:.2f}s "
        f"in_read_model={len(matched_ids)}/100"
    )

    assert len(matched_ids) == 100, (
        f"Only {len(matched_ids)}/100 plans appeared in read model within 15s"
    )


# ---------------------------------------------------------------------------
# Data volume with concurrency — 10 users × 100 customers
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@pytest.mark.stress
async def test_10_users_each_creating_100_customers():
    start = time.monotonic()

    async with make_client() as client:
        async def _create_batch(user_index: int) -> list[int]:
            codes = []
            for _ in range(100):
                s = secrets.token_hex(4)
                try:
                    resp = await client.post("/api/customers", json={
                        "name": f"Customer {s}",
                        "address": f"Address {s}",
                    })
                    codes.append(resp.status_code)
                except Exception:
                    codes.append(0)
            return codes

        all_code_lists = await asyncio.gather(*[_create_batch(i) for i in range(10)])
        all_codes = [c for batch in all_code_lists for c in batch]

        list_resp = await client.get("/api/customers")

    elapsed = time.monotonic() - start
    five_xx = [c for c in all_codes if 500 <= c <= 599]
    print(
        f"\n[10u×100c] {elapsed:.2f}s total={len(all_codes)} "
        f"5xx={len(five_xx)} codes={sorted(set(all_codes))}"
    )

    assert len(five_xx) == 0, f"Got {len(five_xx)} 5xx across 1000 customer creations"
    assert list_resp.status_code == 200
    assert isinstance(list_resp.json(), list)


# ---------------------------------------------------------------------------
# 100 full lifecycles concurrently
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@pytest.mark.stress
async def test_100_users_full_lifecycle_concurrently():
    # allow cluster to stabilise after previous heavy test
    await asyncio.sleep(5)
    start = time.monotonic()

    async with make_client() as client:
        async def _lifecycle(i: int) -> list[int]:
            s = secrets.token_hex(4)
            rep = await create_user(client, s + "r", role="sales_rep")
            manager = await create_user(client, s + "m", role="manager")
            rep_id = rep["id"]
            manager_id = manager["id"]

            customer = await create_customer(client, s)
            customer_id = customer["id"]

            plan = await _create_plan(client, rep_id, s)
            plan_id = plan["id"]

            visit_resp = await client.post(f"/api/plans/{plan_id}/visits", json={
                "plan_id": plan_id,
                "customer_id": customer_id,
                "customer_name": customer["name"],
                "scheduled_order": 1,
            })

            confirm_resp = await _confirm_plan(client, plan_id)
            activate_resp = await _activate_plan(client, plan_id)

            expense = await _create_expense(client, rep_id, plan_id, s)
            expense_id = expense["id"]

            submit_resp = await _submit_expense(client, expense_id)
            approve_resp = await _approve_expense(client, expense_id, manager_id)
            complete_resp = await _complete_plan(client, plan_id)

            return [
                visit_resp.status_code,
                confirm_resp.status_code,
                activate_resp.status_code,
                submit_resp.status_code,
                approve_resp.status_code,
                complete_resp.status_code,
            ]

        # 20 concurrent lifecycles — upper bound for KinD laptop cluster
        # 100 concurrent lifecycles exceeds cluster POST capacity;
        # see test_flat_get_customers[asyncio-500] for GET-level limits
        all_results = await asyncio.gather(*[_lifecycle(i) for i in range(20)])

    elapsed = time.monotonic() - start
    all_codes = [c for lifecycle in all_results for c in lifecycle]
    failures = [c for c in all_codes if c >= 400]

    print(
        f"\n[20 concurrent lifecycles] total_time={elapsed:.2f}s "
        f"total_ops={len(all_codes)} failures={len(failures)} "
        f"failure_codes={sorted(set(failures))}"
    )

    assert len(failures) == 0, (
        f"{len(failures)} operations failed across 100 concurrent lifecycles: "
        f"codes={sorted(set(failures))}"
    )


# ---------------------------------------------------------------------------
# 20 managers approving 500 expenses
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@pytest.mark.stress
async def test_20_managers_approving_500_expenses():
    # allow cluster to stabilise after previous heavy test
    await asyncio.sleep(5)
    suffix = secrets.token_hex(4)
    start = time.monotonic()

    async with make_client() as client:
        # Create 20 manager users
        managers = await asyncio.gather(*[
            create_user(client, secrets.token_hex(4) + "mgr", role="manager")
            for _ in range(20)
        ])
        manager_ids = [m["id"] for m in managers]

        rep = await create_user(client, suffix)
        rep_id = rep["id"]

        customer = await create_customer(client, suffix)
        customer_id = customer["id"]
        customer_name = customer["name"]

        plan = await _create_plan(client, rep_id, suffix)
        plan_id = plan["id"]
        await _add_visit(client, plan_id, customer_id, customer_name)
        await _confirm_plan(client, plan_id)

        # Create 500 expenses
        expenses = await asyncio.gather(*[
            _create_expense(client, rep_id, plan_id, secrets.token_hex(4))
            for _ in range(500)
        ])
        expense_ids = [e["id"] for e in expenses]

        # Submit all 500
        await asyncio.gather(*[_submit_expense(client, eid) for eid in expense_ids])

        # Approve all 500 distributed round-robin across 20 managers
        approve_resps = await asyncio.gather(*[
            _approve_expense(client, expense_ids[i], manager_ids[i % 20])
            for i in range(500)
        ])

    elapsed = time.monotonic() - start
    approve_codes = [r.status_code for r in approve_resps]
    approve_bodies = [r.json() for r in approve_resps]
    five_xx = [c for c in approve_codes if 500 <= c <= 599]
    not_200 = [c for c in approve_codes if c != 200]

    print(
        f"\n[20mgr 500exp] {elapsed:.2f}s "
        f"5xx={len(five_xx)} not_200={len(not_200)}"
    )

    assert len(five_xx) == 0, f"Got {len(five_xx)} 5xx on approvals"
    assert len(not_200) == 0, f"Got {len(not_200)} non-200 on approvals"
    for body in approve_bodies:
        assert body.get("status") == "approved", (
            f"Expense not approved: {body.get('status')}"
        )


# ---------------------------------------------------------------------------
# CQRS consistency under concurrent load
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@pytest.mark.stress
async def test_cqrs_consistency_under_concurrent_load():
    suffix = secrets.token_hex(4)
    start = time.monotonic()

    async with make_client() as client:
        rep = await create_user(client, suffix)
        rep_id = rep["id"]

        customer = await create_customer(client, suffix)
        customer_id = customer["id"]
        customer_name = customer["name"]

        async def _create_and_confirm(i: int) -> int:
            try:
                s = secrets.token_hex(4)
                plan = await _create_plan(client, rep_id, s)
                plan_id = plan["id"]
                await _add_visit(client, plan_id, customer_id, customer_name)
                confirm_resp = await _confirm_plan(client, plan_id)
                return confirm_resp.status_code
            except Exception:
                return 0

        async def _read_history() -> tuple[int, object]:
            try:
                resp = await client.get(
                    "/api/plans/read/history",
                    params={"rep_id": rep_id},
                )
                return resp.status_code, resp.json()
            except Exception:
                return 0, None

        write_tasks = [_create_and_confirm(i) for i in range(20)]
        read_tasks = [_read_history() for _ in range(20)]

        results = await asyncio.gather(*write_tasks, *read_tasks)

    elapsed = time.monotonic() - start
    write_codes = list(results[:20])
    read_results = list(results[20:])
    read_codes = [code for code, _ in read_results]
    read_bodies_list = [body for _, body in read_results]

    write_5xx = [c for c in write_codes if 500 <= c <= 599]
    read_5xx = [c for c in read_codes if 500 <= c <= 599]

    print(
        f"\n[CQRS load] {elapsed:.2f}s "
        f"write_codes={sorted(set(write_codes))} "
        f"read_codes={sorted(set(read_codes))}"
    )

    assert len(write_5xx) == 0, f"Got {len(write_5xx)} 5xx on plan writes"
    assert len(read_5xx) == 0, f"Got {len(read_5xx)} 5xx on CQRS reads"

    for i, body in enumerate(read_bodies_list):
        assert isinstance(body, list), (
            f"CQRS read {i} returned non-list (error body in place of list): {type(body)}"
        )
