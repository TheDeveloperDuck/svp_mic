import asyncio
import secrets
import statistics
import time

import httpx
import pytest

from tests.stress.conftest import BASE_URL, make_client, create_customer, create_user

STRICT_LEVELS = [1, 2, 5, 10, 20, 25, 50, 75, 100]
DEGRADED_LEVELS = [150, 200, 500]

ALL_LEVELS = STRICT_LEVELS + DEGRADED_LEVELS


async def run_concurrent(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    n: int,
    bodies: list | None = None,
) -> list[int]:
    async def _req(i: int) -> int:
        try:
            body = bodies[i] if bodies else None
            if method.upper() == "GET":
                resp = await client.get(path)
            elif method.upper() == "POST":
                resp = await client.post(path, json=body)
            else:
                resp = await client.request(method.upper(), path, json=body)
            return resp.status_code
        except Exception:
            return 0

    return list(await asyncio.gather(*[_req(i) for i in range(n)]))


# ---------------------------------------------------------------------------
# Flat GET tests — parametrized over all levels
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@pytest.mark.stress
@pytest.mark.parametrize("n", ALL_LEVELS)
async def test_flat_get_customers(n):
    start = time.monotonic()
    async with make_client() as client:
        codes = await run_concurrent(client, "GET", "/api/customers", n)
    elapsed = time.monotonic() - start
    print(f"\n[GET /api/customers n={n}] {elapsed:.2f}s codes={sorted(set(codes))}")

    five_xx = [c for c in codes if 500 <= c <= 599]
    if n in STRICT_LEVELS:
        assert len(five_xx) == 0, f"Got {len(five_xx)} 5xx responses at n={n}"
    else:
        ok = [c for c in codes if c in (200, 429)]
        assert len(codes) > 0, "No responses received"
        assert len(ok) / len(codes) >= 0.50, (
            f"Less than 50% non-5xx at n={n}: {len(ok)}/{len(codes)}"
        )
        assert len(five_xx) < len(codes), "All responses were 5xx — system fully collapsed"


@pytest.mark.anyio
@pytest.mark.stress
@pytest.mark.parametrize("n", ALL_LEVELS)
async def test_flat_get_plans(n):
    start = time.monotonic()
    async with make_client() as client:
        codes = await run_concurrent(client, "GET", "/api/plans", n)
    elapsed = time.monotonic() - start
    print(f"\n[GET /api/plans n={n}] {elapsed:.2f}s codes={sorted(set(codes))}")

    five_xx = [c for c in codes if 500 <= c <= 599]
    if n in STRICT_LEVELS:
        assert len(five_xx) == 0, f"Got {len(five_xx)} 5xx responses at n={n}"
    else:
        ok = [c for c in codes if c in (200, 429)]
        assert len(codes) > 0, "No responses received"
        assert len(ok) / len(codes) >= 0.50, (
            f"Less than 50% non-5xx at n={n}: {len(ok)}/{len(codes)}"
        )
        assert len(five_xx) < len(codes), "All responses were 5xx — system fully collapsed"


@pytest.mark.anyio
@pytest.mark.stress
@pytest.mark.parametrize("n", ALL_LEVELS)
async def test_flat_get_expenses(n):
    start = time.monotonic()
    async with make_client() as client:
        codes = await run_concurrent(client, "GET", "/api/expenses", n)
    elapsed = time.monotonic() - start
    print(f"\n[GET /api/expenses n={n}] {elapsed:.2f}s codes={sorted(set(codes))}")

    five_xx = [c for c in codes if 500 <= c <= 599]
    if n in STRICT_LEVELS:
        assert len(five_xx) == 0, f"Got {len(five_xx)} 5xx responses at n={n}"
    else:
        ok = [c for c in codes if c in (200, 429)]
        assert len(codes) > 0, "No responses received"
        assert len(ok) / len(codes) >= 0.50, (
            f"Less than 50% non-5xx at n={n}: {len(ok)}/{len(codes)}"
        )
        assert len(five_xx) < len(codes), "All responses were 5xx — system fully collapsed"


# ---------------------------------------------------------------------------
# Flat POST tests — strict levels only
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@pytest.mark.stress
@pytest.mark.parametrize("n", STRICT_LEVELS)
async def test_flat_post_customers(n):
    bodies = [
        {
            "name": f"Customer {secrets.token_hex(4)}",
            "address": f"Address {secrets.token_hex(4)}",
        }
        for _ in range(n)
    ]
    start = time.monotonic()
    async with make_client() as client:
        codes = await run_concurrent(client, "POST", "/api/customers", n, bodies=bodies)
    elapsed = time.monotonic() - start
    print(f"\n[POST /api/customers n={n}] {elapsed:.2f}s codes={sorted(set(codes))}")
    five_xx = [c for c in codes if 500 <= c <= 599]
    assert len(five_xx) == 0, f"Got {len(five_xx)} 5xx responses at n={n}"


@pytest.mark.anyio
@pytest.mark.stress
@pytest.mark.parametrize("n", STRICT_LEVELS)
async def test_flat_post_users(n):
    bodies = [
        {
            "name": f"User {secrets.token_hex(4)}",
            "email": f"user_{secrets.token_hex(8)}@example.com",
            "password": "testpassword",
            "role": "sales_rep",
        }
        for _ in range(n)
    ]
    start = time.monotonic()
    async with make_client() as client:
        codes = await run_concurrent(client, "POST", "/api/users", n, bodies=bodies)
    elapsed = time.monotonic() - start
    print(f"\n[POST /api/users n={n}] {elapsed:.2f}s codes={sorted(set(codes))}")
    five_xx = [c for c in codes if 500 <= c <= 599]
    assert len(five_xx) == 0, f"Got {len(five_xx)} 5xx responses at n={n}"


# ---------------------------------------------------------------------------
# Overload tests — named, not parametrized
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@pytest.mark.stress
async def test_overload_150_concurrent_customers():
    # allow cluster to recover after heavy POST tests
    await asyncio.sleep(10)
    n = 150
    start = time.monotonic()
    async with make_client() as client:
        codes = await run_concurrent(client, "GET", "/api/customers", n)
    elapsed = time.monotonic() - start
    received = [c for c in codes if c != 0]
    ok = [c for c in codes if c == 200]
    print(
        f"\n[overload n=150] {elapsed:.2f}s received={len(received)} "
        f"ok={len(ok)} codes={sorted(set(codes))}"
    )
    assert len(received) > 0, "No responses received at n=150"
    assert len(ok) / n >= 0.75, (
        f"Less than 75% 200 at n=150: {len(ok)}/{n}"
    )
    five_xx = [c for c in codes if 500 <= c <= 599]
    assert len(five_xx) < n, "All responses were 5xx or connection errors"


@pytest.mark.anyio
@pytest.mark.stress
async def test_overload_200_concurrent_customers():
    # allow cluster to recover after heavy POST tests
    await asyncio.sleep(5)
    n = 200
    start = time.monotonic()
    async with make_client() as client:
        codes = await run_concurrent(client, "GET", "/api/customers", n)
    elapsed = time.monotonic() - start
    received = [c for c in codes if c != 0]
    ok = [c for c in codes if c == 200]
    print(
        f"\n[overload n=200] {elapsed:.2f}s received={len(received)} "
        f"ok={len(ok)} codes={sorted(set(codes))}"
    )
    assert len(received) > 0, "No responses received at n=200"
    assert len(ok) / n >= 0.50, (
        f"Less than 50% 200 at n=200: {len(ok)}/{n}"
    )


@pytest.mark.anyio
@pytest.mark.stress
async def test_overload_500_concurrent_customers():
    n = 500
    start = time.monotonic()
    async with make_client() as client:
        codes = await run_concurrent(client, "GET", "/api/customers", n)
    elapsed = time.monotonic() - start

    received = [c for c in codes if c != 0]
    ok = [c for c in codes if c == 200]
    five_xx = [c for c in codes if 500 <= c <= 599]
    success_rate = len(ok) / n if n else 0
    error_rate = len(five_xx) / n if n else 0

    print(
        f"\n[overload n=500] total_time={elapsed:.2f}s "
        f"received={len(received)} success_rate={success_rate:.1%} "
        f"error_rate={error_rate:.1%} codes={sorted(set(codes))}"
    )

    assert len(received) > 0, "No responses received at n=500"
    assert len(five_xx) < n, "All responses were 5xx — system fully collapsed"
