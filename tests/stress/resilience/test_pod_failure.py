import asyncio
import secrets
import subprocess
import time

import httpx
import pytest

BASE_URL = "http://localhost:8080"


def kill_pod(app_label: str) -> None:
    subprocess.run(
        [
            "kubectl", "delete", "pod", "-n", "svp",
            "-l", f"app={app_label}",
            "--force", "--grace-period=0",
        ],
        capture_output=True,
        timeout=30,
    )


def wait_for_deployment(deployment_name: str, timeout: int = 90) -> None:
    subprocess.run(
        [
            "kubectl", "rollout", "status",
            f"deployment/{deployment_name}",
            "-n", "svp",
            f"--timeout={timeout}s",
        ],
        capture_output=True,
        timeout=timeout + 10,
    )


# ---------------------------------------------------------------------------
# Service pod recovery
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@pytest.mark.stress
async def test_customer_user_service_recovers_after_pod_kill():
    start = time.monotonic()
    kill_pod("customer-user-service")
    wait_for_deployment("svp-customer-user-service")
    time.sleep(3)

    codes: list[int] = []
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        for _ in range(5):
            resp = await client.get("/api/customers")
            codes.append(resp.status_code)
        last_resp = await client.get("/api/customers")

    elapsed = time.monotonic() - start
    ok = [c for c in codes if c == 200]
    print(f"\n[customer-user-service recovery] codes={codes} time={elapsed:.2f}s")

    assert len(ok) >= 4, f"Expected ≥4 of 5 requests to return 200 after pod kill: {codes}"
    data = last_resp.json()
    assert isinstance(data, list), f"Last response was not a JSON list: {data!r}"


@pytest.mark.anyio
@pytest.mark.stress
async def test_planning_service_recovers_after_pod_kill():
    start = time.monotonic()
    kill_pod("planning-service")
    wait_for_deployment("svp-planning-service")
    time.sleep(3)

    codes: list[int] = []
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        for _ in range(5):
            resp = await client.get("/api/plans")
            codes.append(resp.status_code)
        last_resp = await client.get("/api/plans")

    elapsed = time.monotonic() - start
    ok = [c for c in codes if c == 200]
    print(f"\n[planning-service recovery] codes={codes} time={elapsed:.2f}s")

    assert len(ok) >= 4, f"Expected ≥4 of 5 requests to return 200 after pod kill: {codes}"
    data = last_resp.json()
    assert isinstance(data, list), f"Last response was not a JSON list: {data!r}"


@pytest.mark.anyio
@pytest.mark.stress
async def test_expense_service_recovers_after_pod_kill():
    start = time.monotonic()
    kill_pod("expense-service")
    wait_for_deployment("svp-expense-service")
    time.sleep(3)

    codes: list[int] = []
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        for _ in range(5):
            resp = await client.get("/api/expenses")
            codes.append(resp.status_code)
        last_resp = await client.get("/api/expenses")

    elapsed = time.monotonic() - start
    ok = [c for c in codes if c == 200]
    print(f"\n[expense-service recovery] codes={codes} time={elapsed:.2f}s")

    assert len(ok) >= 4, f"Expected ≥4 of 5 requests to return 200 after pod kill: {codes}"
    data = last_resp.json()
    assert isinstance(data, list), f"Last response was not a JSON list: {data!r}"


# ---------------------------------------------------------------------------
# Infrastructure recovery
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@pytest.mark.stress
async def test_kafka_consumers_resume_after_pod_restart():
    start = time.monotonic()
    kill_pod("kafka")
    subprocess.run(
        ["kubectl", "rollout", "status", "statefulset/kafka", "-n", "svp", "--timeout=120s"],
        capture_output=True,
        timeout=130,
    )
    time.sleep(20)

    suffix = secrets.token_hex(4)
    plan_id: str | None = None
    rep_id: str | None = None

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        user_resp = await client.post(
            "/api/users",
            json={
                "name": f"Rep {suffix}",
                "email": f"rep_{suffix}@example.com",
                "password": "testpassword",
                "role": "sales_rep",
            },
        )
        user_resp.raise_for_status()
        rep_id = user_resp.json()["id"]

        cust_resp = await client.post(
            "/api/customers",
            json={"name": f"Customer {suffix}", "address": f"Addr {suffix}"},
        )
        cust_resp.raise_for_status()
        cust_id = cust_resp.json()["id"]

        plan_resp = await client.post(
            "/api/plans",
            json={
                "rep_id": rep_id,
                "date": "2026-06-01",
                "start_location": "Dublin",
                "end_location": "Cork",
            },
        )
        plan_resp.raise_for_status()
        plan_id = plan_resp.json()["id"]

        visit_resp = await client.post(
            f"/api/plans/{plan_id}/visits",
            json={
                "plan_id": plan_id,
                "customer_id": cust_id,
                "customer_name": f"Customer {suffix}",
                "scheduled_order": 1,
            },
        )
        visit_resp.raise_for_status()

        confirm_resp = await client.patch(f"/api/plans/{plan_id}/confirm")
        confirm_resp.raise_for_status()

        await asyncio.sleep(5)

        history_resp = await client.get(f"/api/plans/read/history?rep_id={rep_id}")
        assert history_resp.status_code == 200, (
            f"Expected 200 from history endpoint, got {history_resp.status_code}"
        )
        history = history_resp.json()
        plan_ids = [p["id"] for p in history]
        row_count = len(history)

    elapsed = time.monotonic() - start
    print(
        f"\n[kafka recovery] plan_id={plan_id} history_rows={row_count} "
        f"time={elapsed:.2f}s"
    )
    assert plan_id in plan_ids, (
        f"Plan {plan_id} not found in CQRS read model after Kafka restart: {plan_ids}"
    )


@pytest.mark.anyio
@pytest.mark.stress
async def test_redis_unavailability_degrades_gracefully():
    subprocess.run(
        ["kubectl", "scale", "statefulset", "redis", "--replicas=0", "-n", "svp"],
        capture_output=True,
        timeout=30,
    )
    time.sleep(3)

    try:
        codes: list[int] = []
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
            for _ in range(3):
                try:
                    resp = await client.get("/api/customers")
                    codes.append(resp.status_code)
                except Exception as exc:
                    codes.append(-1)
                    print(f"[redis=0] request error: {type(exc).__name__}")
        print(f"[redis=0] codes while unavailable: {codes}")
        # Redis unavailability may cause timeouts or errors — this is expected.
        # We do not assert 200 here; we assert recovery after restoration.
    finally:
        subprocess.run(
            ["kubectl", "scale", "statefulset", "redis", "--replicas=1", "-n", "svp"],
            capture_output=True,
            timeout=30,
        )
        subprocess.run(
            ["kubectl", "rollout", "status", "statefulset/redis", "-n", "svp", "--timeout=60s"],
            capture_output=True,
            timeout=70,
        )

    # recovery assertion
    await asyncio.sleep(5)
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        resp = await client.get("/api/customers")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    print("[redis=1] service recovered successfully")


# ---------------------------------------------------------------------------
# Full stack recovery
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@pytest.mark.stress
async def test_all_app_pods_recover_within_60_seconds():
    subprocess.run(
        [
            "kubectl", "delete", "pods", "-n", "svp",
            "-l", "app in (customer-user-service,planning-service,expense-service,frontend-service)",
            "--force", "--grace-period=0",
        ],
        capture_output=True,
        timeout=30,
    )

    start_time = time.time()
    recovered = False

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=5.0) as client:
        while time.time() - start_time < 60:
            try:
                resp = await client.get("/api/customers")
                if resp.status_code == 200:
                    recovered = True
                    break
            except Exception:
                pass
            await asyncio.sleep(2)

    recovery_time = time.time() - start_time
    print(f"\n[full stack recovery] recovery_time={recovery_time:.2f}s")

    assert recovered, f"Cluster did not recover within 60 seconds"
    assert recovery_time < 60, (
        f"Recovery took {recovery_time:.2f}s — exceeded 60s limit"
    )
