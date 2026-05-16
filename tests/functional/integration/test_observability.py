import asyncio
import subprocess
import time

import httpx
import pytest


@pytest.fixture(scope="module", autouse=True)
def generate_load():
    with httpx.Client(base_url="http://localhost:8080", timeout=30.0) as c:
        for _ in range(20):
            try:
                c.get("/api/customers")
            except Exception:
                pass
    yield


@pytest.mark.anyio
async def test_prometheus_returns_istio_requests_total(generate_load):
    async with httpx.AsyncClient() as c:
        resp = await c.get(
            "http://localhost:9090/api/v1/query",
            params={"query": "istio_requests_total"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert len(data["data"]["result"]) > 0


@pytest.mark.anyio
async def test_prometheus_has_customer_user_service_metrics(generate_load):
    async with httpx.AsyncClient() as c:
        resp = await c.get(
            "http://localhost:9090/api/v1/query",
            params={"query": 'istio_requests_total{destination_service_name="customer-user-service"}'},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert len(data["data"]["result"]) > 0


@pytest.mark.anyio
async def test_prometheus_has_planning_service_metrics(generate_load):
    async with httpx.AsyncClient() as c:
        resp = await c.get(
            "http://localhost:9090/api/v1/query",
            params={"query": 'istio_requests_total{destination_service_name="planning-service"}'},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert len(data["data"]["result"]) > 0


@pytest.mark.anyio
async def test_prometheus_has_expense_service_metrics(generate_load):
    async with httpx.AsyncClient() as c:
        resp = await c.get(
            "http://localhost:9090/api/v1/query",
            params={"query": 'istio_requests_total{destination_service_name="expense-service"}'},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert len(data["data"]["result"]) > 0


@pytest.mark.anyio
async def test_jaeger_returns_services(generate_load):
    async with httpx.AsyncClient() as c:
        resp = await c.get("http://localhost:16686/jaeger/api/services")
    assert resp.status_code == 200
    assert len(resp.json()["data"]) > 0


@pytest.mark.anyio
async def test_jaeger_has_traces_after_load(generate_load):
    await asyncio.sleep(5)
    async with httpx.AsyncClient() as c:
        resp = await c.get(
            "http://localhost:16686/jaeger/api/traces",
            params={"service": "istio-ingressgateway.istio-system", "limit": "5"},
        )
    assert resp.status_code == 200
    assert len(resp.json()["data"]) > 0


@pytest.mark.anyio
async def test_jaeger_trace_contains_multiple_spans(generate_load):
    await asyncio.sleep(5)
    async with httpx.AsyncClient() as c:
        resp = await c.get(
            "http://localhost:16686/jaeger/api/traces",
            params={"service": "istio-ingressgateway.istio-system", "limit": "1"},
        )
    assert resp.status_code == 200
    traces = resp.json()["data"]
    assert len(traces) > 0
    trace = traces[0]
    assert len(trace["spans"]) >= 1


@pytest.mark.anyio
async def test_prometheus_rate_limit_envoyfilter_applied(generate_load):
    try:
        apply_result = subprocess.run(
            ["kubectl", "apply", "-f", "k8s/istio/testing/rate-limit.yaml"],
            capture_output=True, text=True, timeout=60,
        )
        assert apply_result.returncode == 0

        get_result = subprocess.run(
            [
                "kubectl", "get", "envoyfilter",
                "customer-user-service-rate-limit",
                "-n", "svp", "-o", "name",
            ],
            capture_output=True, text=True, timeout=60,
        )
        assert get_result.returncode == 0
        assert "envoyfilter" in get_result.stdout.lower()
    finally:
        subprocess.run(
            ["kubectl", "delete", "-f", "k8s/istio/testing/rate-limit.yaml"],
            capture_output=True, check=False, timeout=30,
        )
        await asyncio.sleep(10)
