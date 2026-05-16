import asyncio
import pathlib
import statistics
import subprocess
import time

import httpx
import pytest

from tests.stress.conftest import make_client

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent.parent
FAULT_DELAY_FILE = PROJECT_ROOT / "k8s/istio/testing/fault-injection-gateway.yaml"
FAULT_ABORT_FILE = PROJECT_ROOT / "k8s/istio/testing/fault-injection-expense-gateway.yaml"
RESTORE_VS_FILE = PROJECT_ROOT / "k8s/istio/virtual-services.yaml"


def apply_manifest(path: pathlib.Path) -> None:
    subprocess.run(
        ["kubectl", "apply", "-f", str(path)],
        capture_output=True,
        check=True,
        timeout=30,
    )


def restore_virtual_services() -> None:
    subprocess.run(
        ["kubectl", "apply", "-f", str(RESTORE_VS_FILE)],
        capture_output=True,
        check=True,
        timeout=30,
    )
    time.sleep(3)


async def measure_latencies(
    client: httpx.AsyncClient, n: int = 10, path: str = "/api/customers"
) -> list[float]:
    latencies: list[float] = []
    for _ in range(n):
        t = time.monotonic()
        await client.get(path)
        latencies.append(time.monotonic() - t)
    return latencies


# ---------------------------------------------------------------------------
# Delay injection
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@pytest.mark.stress
async def test_delay_injection_increases_median_latency():
    apply_manifest(FAULT_DELAY_FILE)
    try:
        time.sleep(2)
        async with make_client() as client:
            latencies = await measure_latencies(client)
        med = statistics.median(latencies)
        print(
            f"\n[delay injection] median={med:.3f}s "
            f"min={min(latencies):.3f}s max={max(latencies):.3f}s"
        )
        assert med > 1.0, f"Median latency {med:.3f}s not elevated — fault may not have applied"
    finally:
        restore_virtual_services()


@pytest.mark.anyio
@pytest.mark.stress
async def test_baseline_latency_without_fault():
    restore_virtual_services()
    time.sleep(3)
    async with make_client() as client:
        latencies = await measure_latencies(client)
    med = statistics.median(latencies)
    print(f"\n[baseline] median={med:.3f}s")
    assert med < 2.0, f"Baseline median latency {med:.3f}s too high — cluster may be overloaded"
    assert all(lat < 5.0 for lat in latencies), (
        f"Some baseline latencies exceeded 5s: {[round(l, 3) for l in latencies]}"
    )


@pytest.mark.anyio
@pytest.mark.stress
async def test_restore_removes_delay():
    apply_manifest(FAULT_DELAY_FILE)
    time.sleep(2)
    restore_virtual_services()
    time.sleep(3)
    async with make_client() as client:
        latencies = await measure_latencies(client, n=5)
    med = statistics.median(latencies)
    print(f"\n[restore removes delay] latencies={[round(l, 3) for l in latencies]}")
    assert med < 2.0, (
        f"Median latency {med:.3f}s still elevated after restore"
    )


# ---------------------------------------------------------------------------
# Abort injection
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@pytest.mark.stress
async def test_abort_injection_causes_errors_on_expense_service():
    apply_manifest(FAULT_ABORT_FILE)
    try:
        time.sleep(2)
        codes: list[int] = []
        async with make_client() as client:
            for _ in range(20):
                resp = await client.get("/api/expenses/read/history")
                codes.append(resp.status_code)
        non_200 = [c for c in codes if c != 200]
        from collections import Counter
        dist = dict(Counter(codes))
        print(f"\n[abort injection] distribution={dist}")
        assert len(non_200) >= 2, (
            f"Expected ≥2 non-200 responses from abort fault, got {len(non_200)}: {dist}"
        )
    finally:
        restore_virtual_services()


@pytest.mark.anyio
@pytest.mark.stress
async def test_restore_removes_aborts():
    apply_manifest(FAULT_ABORT_FILE)
    time.sleep(2)
    restore_virtual_services()
    time.sleep(3)
    responses: list[httpx.Response] = []
    async with make_client() as client:
        for _ in range(5):
            resp = await client.get("/api/expenses/read/history")
            responses.append(resp)
    codes = [r.status_code for r in responses]
    success = [r for r in responses if r.status_code == 200]
    print(f"\n[restore removes aborts] codes={codes}")
    assert len(success) >= 4, (
        f"Expected ≥4 successful responses after restore, got {len(success)}: {codes}"
    )


# ---------------------------------------------------------------------------
# VirtualService verification
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@pytest.mark.stress
async def test_fault_injection_yaml_exists_and_applies():
    assert FAULT_DELAY_FILE.exists(), f"Missing: {FAULT_DELAY_FILE}"
    assert FAULT_ABORT_FILE.exists(), f"Missing: {FAULT_ABORT_FILE}"

    apply_manifest(FAULT_DELAY_FILE)
    try:
        result = subprocess.run(
            ["kubectl", "get", "virtualservice", "-n", "svp", "-o", "yaml"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"kubectl get virtualservice failed: {result.stderr}"
        assert "fault" in result.stdout, (
            "Expected 'fault' in VirtualService YAML after applying fault manifest"
        )
    finally:
        restore_virtual_services()
        result_after = subprocess.run(
            ["kubectl", "get", "virtualservice", "-n", "svp", "-o", "yaml"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert "fault" not in result_after.stdout, (
            "Expected no 'fault' in VirtualService YAML after restore"
        )
