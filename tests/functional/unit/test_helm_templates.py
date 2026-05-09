import subprocess
from pathlib import Path

import pytest
import yaml

_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
_HELM_CHART = _PROJECT_ROOT / "k8s" / "helm" / "svp"


@pytest.fixture(scope="module")
def helm_output() -> str:
    result = subprocess.run(
        ["helm", "template", "svp-test", str(_HELM_CHART), "--namespace", "test-ns"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_helm_lint_passes():
    result = subprocess.run(
        ["helm", "lint", str(_HELM_CHART)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_helm_template_renders():
    result = subprocess.run(
        ["helm", "template", "svp-test", str(_HELM_CHART), "--namespace", "test-ns"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout.strip() != ""


def test_no_hardcoded_namespace(helm_output):
    assert "namespace: svp" not in helm_output
    assert "namespace: test-ns" in helm_output


def test_secret_contains_postgres_user(helm_output):
    assert "POSTGRES_USER" in helm_output


def test_secret_contains_postgres_password(helm_output):
    assert "POSTGRES_PASSWORD" in helm_output


def test_secret_contains_database_url_customer_user(helm_output):
    assert "DATABASE_URL_CUSTOMER_USER" in helm_output


def test_secret_contains_database_url_planning(helm_output):
    assert "DATABASE_URL_PLANNING" in helm_output


def test_secret_contains_database_url_expense(helm_output):
    assert "DATABASE_URL_EXPENSE" in helm_output


def test_allow_redis_name_not_old_name(helm_output):
    assert "allow-redis-ingress" not in helm_output
    assert "allow-redis" in helm_output


def test_all_four_app_image_names(helm_output):
    assert "svp/customer-user-service:latest" in helm_output
    assert "svp/planning-service:latest" in helm_output
    assert "svp/expense-service:latest" in helm_output
    assert "svp/frontend-service:latest" in helm_output


def test_network_policy_templates_use_release_namespace(helm_output):
    docs = [d for d in yaml.safe_load_all(helm_output) if d]
    for doc in docs:
        if doc.get("kind") == "NetworkPolicy":
            assert doc.get("metadata", {}).get("namespace") != "svp"
