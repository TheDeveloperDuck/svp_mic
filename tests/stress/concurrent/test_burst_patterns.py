import asyncio
import secrets
import statistics
import time

import httpx
import pytest

from tests.stress.conftest import make_client


async def _get_customers(client: httpx.AsyncClient, n: int) -> list[int]:
    async def _req() -> int:
        try:
            resp = await client.get("/api/customers")
            return resp.status_code
        except Exception:
            return 0

    return list(await asyncio.gather(*[_req() for _ in range(n)]))


# ---------------------------------------------------------------------------
# Ramp and hold
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@pytest.mark.stress
async def test_ramp_1_to_100_over_30_seconds_then_hold():
    steps = list(range(10, 110, 10))  # [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    start = time.monotonic()

    async with make_client() as client:
        step_results: list[tuple[int, list[int]]] = []

        for n in steps:
            codes = await _get_customers(client, n)
            step_results.append((n, codes))
            print(
                f"\n[ramp n={n}] codes={sorted(set(codes))} "
                f"5xx={sum(1 for c in codes if 500 <= c <= 599)}"
            )
            await asyncio.sleep(3)

        # Hold phase: 5 rounds of 100 concurrent
        hold_codes: list[int] = []
        for _ in range(5):
            codes = await _get_customers(client, 100)
            hold_codes.extend(codes)
            await asyncio.sleep(2)

    elapsed = time.monotonic() - start
    print(f"\n[ramp+hold] total_time={elapsed:.2f}s")

    # Assert zero 5xx at steps up to and including 50
    for n, codes in step_results:
        five_xx = [c for c in codes if 500 <= c <= 599]
        if n <= 50:
            assert len(five_xx) == 0, (
                f"Got {len(five_xx)} 5xx at ramp step n={n}"
            )
        else:
            ok = [c for c in codes if c == 200]
            assert len(ok) / len(codes) >= 0.80, (
                f"Less than 80% success at ramp step n={n}: {len(ok)}/{len(codes)}"
            )

    # Hold phase: zero 5xx
    hold_5xx = [c for c in hold_codes if 500 <= c <= 599]
    assert len(hold_5xx) == 0, (
        f"Got {len(hold_5xx)} 5xx during hold phase"
    )


# ---------------------------------------------------------------------------
# Ramp, drop, spike
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@pytest.mark.stress
async def test_ramp_drop_spike():
    start = time.monotonic()

    async with make_client() as client:
        # Step 1: ramp from 10 to 100 (10 steps × 10 users), 1s apart
        ramp_results: list[list[int]] = []
        for n in range(10, 110, 10):
            codes = await _get_customers(client, n)
            ramp_results.append(codes)
            await asyncio.sleep(1)

        # Step 2: drop to 10 concurrent for 5 rounds × 1s
        drop_codes: list[int] = []
        for _ in range(5):
            codes = await _get_customers(client, 10)
            drop_codes.extend(codes)
            await asyncio.sleep(1)

        # Step 3: spike to 200 concurrent
        spike_codes = await _get_customers(client, 200)

    elapsed = time.monotonic() - start
    print(f"\n[ramp-drop-spike] total_time={elapsed:.2f}s")

    # Drop phase: all 200, no 5xx
    drop_5xx = [c for c in drop_codes if 500 <= c <= 599]
    non_200_drop = [c for c in drop_codes if c != 200]
    assert len(drop_5xx) == 0, (
        f"Got {len(drop_5xx)} 5xx during drop/recovery phase"
    )
    assert len(non_200_drop) == 0, (
        f"Non-200 responses during drop phase: {sorted(set(non_200_drop))}"
    )

    # Spike phase: at least 50% 200
    spike_ok = [c for c in spike_codes if c == 200]
    assert len(spike_ok) / len(spike_codes) >= 0.50, (
        f"Less than 50% success during spike: {len(spike_ok)}/{len(spike_codes)}"
    )
    print(
        f"[ramp-drop-spike] spike success={len(spike_ok)}/{len(spike_codes)} "
        f"codes={sorted(set(spike_codes))}"
    )


# ---------------------------------------------------------------------------
# Bursty pattern
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@pytest.mark.stress
async def test_bursty_100_users_repeated_5_times():
    start = time.monotonic()
    rounds: list[list[int]] = []

    async with make_client() as client:
        for round_num in range(5):
            codes = await _get_customers(client, 100)
            rounds.append(codes)
            ok = [c for c in codes if c == 200]
            rate = len(ok) / len(codes) if codes else 0
            print(f"\n[burst round={round_num+1}] success_rate={rate:.1%} codes={sorted(set(codes))}")
            if round_num < 4:
                await asyncio.sleep(10)

    elapsed = time.monotonic() - start
    print(f"\n[bursty] total_time={elapsed:.2f}s")

    # Rounds 1 and 2: zero 5xx (fresh pool)
    for i in (0, 1):
        five_xx = [c for c in rounds[i] if 500 <= c <= 599]
        assert len(five_xx) == 0, (
            f"Got {len(five_xx)} 5xx in burst round {i+1}"
        )

    # Rounds 3, 4, 5: at least 90% success
    for i in (2, 3, 4):
        ok = [c for c in rounds[i] if c == 200]
        assert len(ok) / len(rounds[i]) >= 0.90, (
            f"Less than 90% success in burst round {i+1}: {len(ok)}/{len(rounds[i])}"
        )


# ---------------------------------------------------------------------------
# Cold spike
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@pytest.mark.stress
async def test_cold_spike_0_to_100_no_ramp():
    # Drain connection pools
    await asyncio.sleep(5)

    timestamps: list[float] = []
    codes: list[int] = []

    async with make_client() as client:
        async def _timed_req() -> tuple[float, int]:
            t = time.monotonic()
            try:
                resp = await client.get("/api/customers")
                return time.monotonic() - t, resp.status_code
            except Exception:
                return time.monotonic() - t, 0

        overall_start = time.monotonic()
        results = await asyncio.gather(*[_timed_req() for _ in range(100)])

    durations = [d for d, _ in results]
    codes = [c for _, c in results]

    first_response = min(durations)
    last_response = max(durations)
    spread = last_response - first_response

    print(
        f"\n[cold spike n=100] first={first_response:.3f}s "
        f"last={last_response:.3f}s spread={spread:.3f}s "
        f"codes={sorted(set(codes))}"
    )

    five_xx = [c for c in codes if 500 <= c <= 599]
    assert len(five_xx) == 0, (
        f"Got {len(five_xx)} 5xx on cold spike (expected 200 or 429 only)"
    )
    for code in codes:
        assert code in (200, 429), (
            f"Unexpected status code on cold spike: {code}"
        )
