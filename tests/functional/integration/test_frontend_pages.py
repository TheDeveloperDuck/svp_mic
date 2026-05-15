import pytest


@pytest.mark.anyio
async def test_index_page_returns_200(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


@pytest.mark.anyio
async def test_rep_plan_page_returns_200(client):
    resp = await client.get("/rep/plan")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


@pytest.mark.anyio
async def test_rep_execute_page_returns_200(client):
    resp = await client.get("/rep/execute")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


@pytest.mark.anyio
async def test_rep_expenses_page_returns_200(client):
    resp = await client.get("/rep/expenses")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


@pytest.mark.anyio
async def test_manager_expenses_page_returns_200(client):
    resp = await client.get("/manager/expenses")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


@pytest.mark.anyio
async def test_manager_overview_page_returns_200(client):
    resp = await client.get("/manager/overview")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


@pytest.mark.anyio
async def test_admin_users_page_returns_200(client):
    resp = await client.get("/admin/users")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


@pytest.mark.anyio
async def test_admin_customers_page_returns_200(client):
    resp = await client.get("/admin/customers")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
