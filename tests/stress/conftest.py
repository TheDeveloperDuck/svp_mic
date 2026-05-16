import asyncio
import subprocess
import time

import httpx
import pytest

BASE_URL = "http://localhost:8080"


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=BASE_URL, timeout=30.0)


def start_port_forwards() -> None:
    subprocess.run(["pkill", "-f", "port-forward.*8080"], capture_output=True)
    subprocess.run(["pkill", "-f", "port-forward.*9090"], capture_output=True)
    subprocess.run(["pkill", "-f", "port-forward.*16686"], capture_output=True)
    time.sleep(2)
    subprocess.Popen(
        ["kubectl", "port-forward", "-n", "istio-system",
         "svc/istio-ingressgateway", "8080:80"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    subprocess.Popen(
        ["kubectl", "port-forward", "-n", "istio-system",
         "svc/prometheus", "9090:9090"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    subprocess.Popen(
        ["kubectl", "port-forward", "-n", "istio-system",
         "svc/tracing", "16686:80"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(5)


async def create_user(client: httpx.AsyncClient, suffix: str, role: str = "sales_rep") -> dict:
    payload = {
        "name": f"User {suffix}",
        "email": f"user_{suffix}@example.com",
        "password": "testpassword",
        "role": role,
    }
    last_status, last_body = None, None
    for attempt in range(5):
        resp = await client.post("/api/users", json=payload)
        last_status = resp.status_code
        try:
            last_body = resp.json()
        except Exception:
            last_body = resp.text
            print(f"[create_user attempt {attempt+1}] status={last_status} body={last_body!r}")
            await asyncio.sleep(2)
            continue
        if last_status == 201:
            return last_body
        print(f"[create_user attempt {attempt+1}] status={last_status} body={last_body!r}")
        await asyncio.sleep(2)
    raise RuntimeError(f"create_user failed after 5 attempts: status={last_status} body={last_body!r}")


async def create_customer(client: httpx.AsyncClient, suffix: str) -> dict:
    payload = {
        "name": f"Customer {suffix}",
        "address": f"Address {suffix}",
    }
    last_status, last_body = None, None
    for attempt in range(5):
        resp = await client.post("/api/customers", json=payload)
        last_status = resp.status_code
        try:
            last_body = resp.json()
        except Exception:
            last_body = resp.text
            print(f"[create_customer attempt {attempt+1}] status={last_status} body={last_body!r}")
            await asyncio.sleep(2)
            continue
        if last_status == 201:
            return last_body
        print(f"[create_customer attempt {attempt+1}] status={last_status} body={last_body!r}")
        await asyncio.sleep(2)
    raise RuntimeError(f"create_customer failed after 5 attempts: status={last_status} body={last_body!r}")


@pytest.fixture(scope="session", autouse=True)
def stress_session_teardown():
    start_port_forwards()
    yield
    # restart all deployments after stress suite to leave cluster clean
    subprocess.run(
        ["kubectl", "rollout", "restart", "deployment", "-n", "svp"],
        capture_output=True, timeout=30,
    )
    subprocess.run(
        ["kubectl", "rollout", "status", "deployment/svp-planning-service",
         "-n", "svp", "--timeout=120s"],
        capture_output=True, timeout=130,
    )
    time.sleep(90)
    start_port_forwards()
    print("\n[stress teardown] cluster restarted, port-forwards restored")


def pytest_configure(config):
    config.addinivalue_line("markers", "stress: stress / load tests, run separately")
    config.addinivalue_line("markers", "anyio: mark test as async anyio")
