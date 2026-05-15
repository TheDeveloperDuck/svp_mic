import json
import subprocess

import pytest


def test_customer_user_service_tls_strict():
    result = subprocess.run(
        ["kubectl", "get", "peerauthentication", "-n", "svp", "-o", "yaml"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0
    assert "mode: STRICT" in result.stdout


def test_planning_service_tls_strict():
    result = subprocess.run(
        ["kubectl", "get", "peerauthentication", "-n", "svp", "-o", "yaml"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0
    assert "mode: STRICT" in result.stdout


def test_expense_service_tls_strict():
    result = subprocess.run(
        ["kubectl", "get", "peerauthentication", "-n", "svp", "-o", "yaml"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0
    assert "mode: STRICT" in result.stdout


def test_frontend_service_tls_strict():
    result = subprocess.run(
        ["kubectl", "get", "peerauthentication", "-n", "svp", "-o", "yaml"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0
    assert "mode: STRICT" in result.stdout


def test_all_app_pods_have_sidecar_injected():
    result = subprocess.run(
        ["kubectl", "get", "pods", "-n", "svp", "-o", "json"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0
    pods = json.loads(result.stdout)["items"]
    app_pods = [p for p in pods if p["metadata"]["name"].startswith("svp-")]
    assert len(app_pods) > 0
    for pod in app_pods:
        container_statuses = pod["status"].get("containerStatuses", [])
        assert len(container_statuses) == 2, (
            f"Pod {pod['metadata']['name']} has {len(container_statuses)} containers, expected 2 (app + sidecar)"
        )


def test_curl_without_sidecar_to_customer_user_service_fails():
    result = subprocess.run(
        [
            "kubectl", "exec", "-n", "svp", "redis-0", "--",
            "wget", "-qO-", "--timeout=3", "http://customer-user-service:8001/health",
        ],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode != 0 or result.stdout.strip() == ""


def test_curl_without_sidecar_to_planning_service_fails():
    result = subprocess.run(
        [
            "kubectl", "exec", "-n", "svp", "redis-0", "--",
            "wget", "-qO-", "--timeout=3", "http://planning-service:8002/health",
        ],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode != 0 or result.stdout.strip() == ""


def test_curl_without_sidecar_to_expense_service_fails():
    result = subprocess.run(
        [
            "kubectl", "exec", "-n", "svp", "redis-0", "--",
            "wget", "-qO-", "--timeout=3", "http://expense-service:8003/health",
        ],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode != 0 or result.stdout.strip() == ""
