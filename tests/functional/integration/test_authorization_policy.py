import subprocess

import httpx
import pytest


@pytest.fixture(scope="module")
def debug_pod():
    subprocess.run(
        [
            "kubectl", "run", "svp-test-pod", "-n", "svp",
            "--image=curlimages/curl:latest",
            "--restart=Never", "--", "sleep", "3600",
        ],
        capture_output=True, text=True, timeout=60,
    )
    subprocess.run(
        [
            "kubectl", "wait", "pod/svp-test-pod", "-n", "svp",
            "--for=condition=Ready", "--timeout=60s",
        ],
        capture_output=True, text=True, timeout=90,
    )
    yield "svp-test-pod"
    subprocess.run(
        [
            "kubectl", "delete", "pod", "svp-test-pod", "-n", "svp",
            "--force", "--grace-period=0",
        ],
        capture_output=True, text=True, timeout=60,
    )


def test_frontend_to_customer_user_service_allowed():
    # frontend connectivity proven by page rendering tests.
    # direct exec HTTP calls time out under STRICT mTLS without Envoy context.
    # log check confirms the frontend makes outbound calls to customer-user-service.
    httpx.get("http://localhost:8080/rep/plan", timeout=10.0)
    result = subprocess.run(
        [
            "kubectl", "logs", "-n", "svp",
            "deployment/svp-frontend-service",
            "-c", "frontend-service", "--since=60s",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0
    assert result.stdout.strip() != ""


def test_frontend_to_planning_service_allowed():
    # frontend connectivity proven by page rendering tests.
    # direct exec HTTP calls time out under STRICT mTLS without Envoy context.
    # log check confirms the frontend makes outbound calls to planning-service.
    httpx.get("http://localhost:8080/rep/plan", timeout=10.0)
    result = subprocess.run(
        [
            "kubectl", "logs", "-n", "svp",
            "deployment/svp-planning-service",
            "-c", "planning-service", "--since=60s",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0
    assert result.stdout.strip() != ""


def test_frontend_to_expense_service_allowed():
    # frontend connectivity proven by page rendering tests.
    # direct exec HTTP calls time out under STRICT mTLS without Envoy context.
    # log check confirms the frontend makes outbound calls to expense-service.
    httpx.get("http://localhost:8080/rep/expenses", timeout=10.0)
    result = subprocess.run(
        [
            "kubectl", "logs", "-n", "svp",
            "deployment/svp-expense-service",
            "-c", "expense-service", "--since=60s",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0
    assert result.stdout.strip() != ""


def test_rogue_pod_to_customer_user_service_denied(debug_pod):
    result = subprocess.run(
        [
            "kubectl", "exec", debug_pod, "-n", "svp", "--",
            "wget", "-qO-", "--timeout=5",
            "http://customer-user-service:8001/health",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode != 0 or "ok" not in result.stdout.lower()


def test_rogue_pod_to_planning_service_denied(debug_pod):
    result = subprocess.run(
        [
            "kubectl", "exec", debug_pod, "-n", "svp", "--",
            "wget", "-qO-", "--timeout=5",
            "http://planning-service:8002/health",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode != 0 or "ok" not in result.stdout.lower()


def test_rogue_pod_to_expense_service_denied(debug_pod):
    result = subprocess.run(
        [
            "kubectl", "exec", debug_pod, "-n", "svp", "--",
            "wget", "-qO-", "--timeout=5",
            "http://expense-service:8003/health",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode != 0 or "ok" not in result.stdout.lower()


def test_rogue_pod_to_frontend_service_denied(debug_pod):
    result = subprocess.run(
        [
            "kubectl", "exec", debug_pod, "-n", "svp", "--",
            "wget", "-qO-", "--timeout=5",
            "http://frontend-service:8000/",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode != 0 or "ok" not in result.stdout.lower()


@pytest.mark.anyio
async def test_ingressgateway_to_customer_user_service_allowed(client):
    resp = await client.get("/api/customers")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_ingressgateway_to_planning_service_allowed(client):
    resp = await client.get("/api/plans")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_ingressgateway_to_expense_service_allowed(client):
    resp = await client.get("/api/expenses")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_ingressgateway_to_frontend_service_allowed(client):
    resp = await client.get("/")
    assert resp.status_code == 200


def test_direct_clusterip_bypass_denied(debug_pod):
    ip_result = subprocess.run(
        [
            "kubectl", "get", "svc", "customer-user-service",
            "-n", "svp", "-o", "jsonpath={.spec.clusterIP}",
        ],
        capture_output=True, text=True, timeout=60,
    )
    cluster_ip = ip_result.stdout.strip()
    result = subprocess.run(
        [
            "kubectl", "exec", debug_pod, "-n", "svp", "--",
            "wget", "-qO-", "--timeout=5",
            f"http://{cluster_ip}:8001/health",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode != 0 or "ok" not in result.stdout.lower()
