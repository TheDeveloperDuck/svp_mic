import secrets

import httpx
import pytest

pytest_plugins = ("anyio",)


@pytest.fixture(scope="function")
async def client():
    async with httpx.AsyncClient(base_url="http://localhost:8080", timeout=30.0) as c:
        yield c


@pytest.fixture(scope="function")
def unique_suffix():
    return secrets.token_hex(4)


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "stress: stress tests, run separately from functional suite"
    )
