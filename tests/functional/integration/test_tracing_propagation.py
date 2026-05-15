import secrets
import subprocess

import pytest


@pytest.mark.anyio
async def test_traceid_logged_by_customer_user_service(client):
    trace_id = secrets.token_hex(16)
    resp = await client.get("/api/customers", headers={"x-b3-traceid": trace_id})
    assert resp.status_code == 200
    result = subprocess.run(
        [
            "kubectl", "logs", "-n", "svp",
            "deployment/svp-customer-user-service",
            "-c", "customer-user-service",
            "--since=15s",
        ],
        capture_output=True, text=True, timeout=30,
    )
    assert "trace_id=" in result.stdout


@pytest.mark.anyio
async def test_traceid_logged_by_planning_service(client):
    trace_id = secrets.token_hex(16)
    resp = await client.get("/api/plans", headers={"x-b3-traceid": trace_id})
    assert resp.status_code == 200
    result = subprocess.run(
        [
            "kubectl", "logs", "-n", "svp",
            "deployment/svp-planning-service",
            "-c", "planning-service",
            "--since=15s",
        ],
        capture_output=True, text=True, timeout=30,
    )
    assert "trace_id=" in result.stdout


@pytest.mark.anyio
async def test_traceid_logged_by_expense_service(client):
    trace_id = secrets.token_hex(16)
    resp = await client.get("/api/expenses", headers={"x-b3-traceid": trace_id})
    assert resp.status_code == 200
    result = subprocess.run(
        [
            "kubectl", "logs", "-n", "svp",
            "deployment/svp-expense-service",
            "-c", "expense-service",
            "--since=15s",
        ],
        capture_output=True, text=True, timeout=30,
    )
    assert "trace_id=" in result.stdout


@pytest.mark.anyio
async def test_traceid_logged_by_frontend_service(client):
    trace_id = secrets.token_hex(16)
    resp = await client.get("/", headers={"x-b3-traceid": trace_id})
    assert resp.status_code == 200
    result = subprocess.run(
        [
            "kubectl", "logs", "-n", "svp",
            "deployment/svp-frontend-service",
            "-c", "frontend-service",
            "--since=15s",
        ],
        capture_output=True, text=True, timeout=30,
    )
    assert "trace_id=" in result.stdout


@pytest.mark.anyio
async def test_request_without_tracing_headers_returns_200_customer(client):
    resp = await client.get("/api/customers")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_request_without_tracing_headers_returns_200_planning(client):
    resp = await client.get("/api/plans")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_request_without_tracing_headers_returns_200_expense(client):
    resp = await client.get("/api/expenses")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_all_seven_b3_headers_do_not_cause_500(client):
    trace_id = secrets.token_hex(16)
    span_id = secrets.token_hex(8)
    parent_span_id = secrets.token_hex(8)
    resp = await client.get(
        "/api/customers",
        headers={
            "x-request-id": secrets.token_hex(8),
            "x-b3-traceid": trace_id,
            "x-b3-spanid": span_id,
            "x-b3-parentspanid": parent_span_id,
            "x-b3-sampled": "1",
            "x-b3-flags": "0",
            "x-forwarded-for": "127.0.0.1",
        },
    )
    assert resp.status_code != 500


@pytest.mark.anyio
async def test_frontend_propagates_traceid_to_customer_service(client):
    trace_id = secrets.token_hex(16)
    resp = await client.get("/rep/plan", headers={"x-b3-traceid": trace_id})
    assert resp.status_code == 200
    result = subprocess.run(
        [
            "kubectl", "logs", "-n", "svp",
            "deployment/svp-customer-user-service",
            "-c", "customer-user-service",
            "--since=15s",
        ],
        capture_output=True, text=True, timeout=30,
    )
    assert "trace_id=" in result.stdout
