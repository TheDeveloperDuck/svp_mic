import asyncio
import pathlib
import subprocess
import time

import httpx
import pytest

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent.parent
RATE_LIMIT_FILE = PROJECT_ROOT / "k8s/istio/testing/rate-limit.yaml"

BASE_URL = "http://localhost:8080"


@pytest.fixture(scope="module")
def apply_rate_limit():
    # Clean up any leftover state from a previous run before applying
    subprocess.run(
        ["kubectl", "delete", "-f", str(RATE_LIMIT_FILE)],
        capture_output=True,
        timeout=30,
    )
    subprocess.run(
        ["kubectl", "apply", "-f", str(RATE_LIMIT_FILE)],
        capture_output=True,
        check=True,
        timeout=30,
    )
    time.sleep(5)
    yield
    subprocess.run(
        ["kubectl", "delete", "-f", str(RATE_LIMIT_FILE)],
        capture_output=True,
        timeout=30,
    )


async def burst_get(
    client: httpx.AsyncClient, n: int, path: str = "/api/customers"
) -> list[httpx.Response]:
    async def _req() -> httpx.Response:
        return await client.get(path)

    return list(await asyncio.gather(*[_req() for _ in range(n)]))


# ---------------------------------------------------------------------------
# At-limit tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@pytest.mark.stress
async def test_8_sequential_requests_succeed(apply_rate_limit):
    time.sleep(1)
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        codes: list[int] = []
        for _ in range(8):
            resp = await client.get("/api/customers")
            codes.append(resp.status_code)
            await asyncio.sleep(0.15)
    assert all(c == 200 for c in codes), (
        f"Expected all 8 sequential requests to return 200, got: {codes}"
    )


@pytest.mark.anyio
@pytest.mark.stress
async def test_token_bucket_refills_after_one_second(apply_rate_limit):
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # Exhaust the token bucket
        await burst_get(client, 20)
        await asyncio.sleep(1.5)
        # Bucket should have refilled
        codes: list[int] = []
        for _ in range(5):
            resp = await client.get("/api/customers")
            codes.append(resp.status_code)
    ok = [c for c in codes if c == 200]
    assert len(ok) >= 4, (
        f"Expected ≥4 of 5 requests to succeed after bucket refill, got: {codes}"
    )


# ---------------------------------------------------------------------------
# Over-limit tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@pytest.mark.stress
async def test_rate_limit_applied_and_requests_succeed(apply_rate_limit):
    time.sleep(1)
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        responses = await burst_get(client, 15)
    codes = [r.status_code for r in responses]
    from collections import Counter
    dist = dict(Counter(codes))
    result = subprocess.run(
        ["kubectl", "get", "envoyfilter",
         "customer-user-service-rate-limit", "-n", "svp", "-o", "name"],
        capture_output=True, text=True, timeout=30,
    )
    print(
        f"\n[rate limit 15 concurrent] distribution={dist} "
        f"envoyfilter_present={'envoyfilter' in result.stdout.lower()}"
    )
    assert len(codes) == 15
    assert all(c in (200, 429) for c in codes)
    assert result.returncode == 0
    assert "envoyfilter" in result.stdout.lower()


@pytest.mark.anyio
@pytest.mark.stress
async def test_25_concurrent_requests_all_non_5xx(apply_rate_limit):
    time.sleep(1)
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        responses = await burst_get(client, 25)
    codes = [r.status_code for r in responses]
    count_200 = codes.count(200)
    count_429 = codes.count(429)
    print(f"\n[rate limit 25 concurrent] 200={count_200} 429={count_429} all_non_5xx={all(c in (200, 429) for c in codes)}")
    assert all(c in (200, 429) for c in codes), (
        f"Expected all responses to be 200 or 429, got: {sorted(set(codes))}"
    )
    assert 200 in codes, f"Expected at least one 200 in 25 concurrent requests: {codes}"


@pytest.mark.anyio
@pytest.mark.stress
async def test_429_response_carries_rate_limit_header(apply_rate_limit):
    time.sleep(1)
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        responses = await burst_get(client, 25)
    rate_limited = [r for r in responses if r.status_code == 429]
    assert len(rate_limited) >= 1, "Expected at least one 429 response"
    first_429 = rate_limited[0]
    assert "x-local-rate-limit" in first_429.headers, (
        f"Expected x-local-rate-limit header on 429 response; "
        f"headers present: {dict(first_429.headers)}"
    )


# ---------------------------------------------------------------------------
# Isolation tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@pytest.mark.stress
async def test_rate_limit_does_not_affect_planning_service(apply_rate_limit):
    time.sleep(1)
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        responses = await burst_get(client, 15, path="/api/plans")
    codes = [r.status_code for r in responses]
    assert all(c == 200 for c in codes), (
        f"Planning service affected by customer rate limit: {codes}"
    )


@pytest.mark.anyio
@pytest.mark.stress
async def test_rate_limit_does_not_affect_expense_service(apply_rate_limit):
    time.sleep(1)
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        responses = await burst_get(client, 15, path="/api/expenses")
    codes = [r.status_code for r in responses]
    assert all(c == 200 for c in codes), (
        f"Expense service affected by customer rate limit: {codes}"
    )
