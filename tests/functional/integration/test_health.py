import subprocess
import time

import httpx
import pytest


def port_forward(service_name, local_port, remote_port, namespace="svp"):
    proc = subprocess.Popen(
        [
            "kubectl", "port-forward",
            f"svc/{service_name}",
            f"{local_port}:{remote_port}",
            "-n", namespace,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(2)
    yield local_port
    proc.terminate()
    proc.wait()


@pytest.fixture(scope="module")
def customer_user_health_port():
    yield from port_forward("customer-user-service", 18001, 8001)


@pytest.fixture(scope="module")
def planning_health_port():
    yield from port_forward("planning-service", 18002, 8002)


@pytest.fixture(scope="module")
def expense_health_port():
    yield from port_forward("expense-service", 18003, 8003)


@pytest.fixture(scope="module")
def frontend_health_port():
    yield from port_forward("frontend-service", 18000, 8000)


# ---------------------------------------------------------------------------
# Status code tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_customer_user_service_health_returns_200(customer_user_health_port):
    async with httpx.AsyncClient() as c:
        resp = await c.get(f"http://localhost:{customer_user_health_port}/health")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_planning_service_health_returns_200(planning_health_port):
    async with httpx.AsyncClient() as c:
        resp = await c.get(f"http://localhost:{planning_health_port}/health")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_expense_service_health_returns_200(expense_health_port):
    async with httpx.AsyncClient() as c:
        resp = await c.get(f"http://localhost:{expense_health_port}/health")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_frontend_service_health_returns_200(frontend_health_port):
    async with httpx.AsyncClient() as c:
        resp = await c.get(f"http://localhost:{frontend_health_port}/health")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Body tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_customer_user_service_health_body_ok(customer_user_health_port):
    async with httpx.AsyncClient() as c:
        resp = await c.get(f"http://localhost:{customer_user_health_port}/health")
    assert resp.json()["status"] == "ok"


@pytest.mark.anyio
async def test_planning_service_health_body_ok(planning_health_port):
    async with httpx.AsyncClient() as c:
        resp = await c.get(f"http://localhost:{planning_health_port}/health")
    assert resp.json()["status"] == "ok"


@pytest.mark.anyio
async def test_expense_service_health_body_ok(expense_health_port):
    async with httpx.AsyncClient() as c:
        resp = await c.get(f"http://localhost:{expense_health_port}/health")
    assert resp.json()["status"] == "ok"


@pytest.mark.anyio
async def test_frontend_service_health_body_ok(frontend_health_port):
    async with httpx.AsyncClient() as c:
        resp = await c.get(f"http://localhost:{frontend_health_port}/health")
    assert resp.json()["status"] == "ok"
