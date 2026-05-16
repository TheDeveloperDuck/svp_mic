import json
import subprocess


def _get_migrate_init_container(pod_json):
    for status in pod_json["status"].get("initContainerStatuses", []):
        name = status.get("name", "")
        if any(kw in name for kw in ("migrate", "alembic", "init")):
            return status
    return None


def test_customer_user_service_init_container_exited_zero():
    result = subprocess.run(
        [
            "kubectl", "get", "pod", "-n", "svp",
            "-l", "app=customer-user-service", "-o", "json",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0
    pods = json.loads(result.stdout)["items"]
    assert len(pods) > 0
    status = _get_migrate_init_container(pods[0])
    assert status is not None, "No migrate/alembic/init init container found"
    assert status["state"]["terminated"]["exitCode"] == 0


def test_planning_service_init_container_exited_zero():
    result = subprocess.run(
        [
            "kubectl", "get", "pod", "-n", "svp",
            "-l", "app=planning-service", "-o", "json",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0
    pods = json.loads(result.stdout)["items"]
    assert len(pods) > 0
    status = _get_migrate_init_container(pods[0])
    assert status is not None, "No migrate/alembic/init init container found"
    assert status["state"]["terminated"]["exitCode"] == 0


def test_expense_service_init_container_exited_zero():
    result = subprocess.run(
        [
            "kubectl", "get", "pod", "-n", "svp",
            "-l", "app=expense-service", "-o", "json",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0
    pods = json.loads(result.stdout)["items"]
    assert len(pods) > 0
    status = _get_migrate_init_container(pods[0])
    assert status is not None, "No migrate/alembic/init init container found"
    assert status["state"]["terminated"]["exitCode"] == 0


def test_customer_user_db_migration_idempotent():
    pod_result = subprocess.run(
        [
            "kubectl", "get", "pod", "-n", "svp",
            "-l", "app=customer-user-service",
            "-o", "jsonpath={.items[0].metadata.name}",
        ],
        capture_output=True, text=True, timeout=60,
    )
    pod = pod_result.stdout.strip()
    result = subprocess.run(
        [
            "kubectl", "exec", "-n", "svp", pod,
            "-c", "customer-user-service", "--",
            "alembic", "-c", "customer_user_service/alembic.ini",
            "upgrade", "head",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0


def test_planning_db_migration_idempotent():
    pod_result = subprocess.run(
        [
            "kubectl", "get", "pod", "-n", "svp",
            "-l", "app=planning-service",
            "-o", "jsonpath={.items[0].metadata.name}",
        ],
        capture_output=True, text=True, timeout=60,
    )
    pod = pod_result.stdout.strip()
    result = subprocess.run(
        [
            "kubectl", "exec", "-n", "svp", pod,
            "-c", "planning-service", "--",
            "alembic", "-c", "planning_service/alembic.ini",
            "upgrade", "head",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0


def test_expense_db_migration_idempotent():
    pod_result = subprocess.run(
        [
            "kubectl", "get", "pod", "-n", "svp",
            "-l", "app=expense-service",
            "-o", "jsonpath={.items[0].metadata.name}",
        ],
        capture_output=True, text=True, timeout=60,
    )
    pod = pod_result.stdout.strip()
    result = subprocess.run(
        [
            "kubectl", "exec", "-n", "svp", pod,
            "-c", "expense-service", "--",
            "alembic", "-c", "expense_service/alembic.ini",
            "upgrade", "head",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0


def test_all_three_services_running_after_migrations():
    result = subprocess.run(
        ["kubectl", "get", "pods", "-n", "svp", "-o", "json"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0
    pods = json.loads(result.stdout)["items"]
    target_labels = {"customer-user-service", "planning-service", "expense-service"}
    for pod in pods:
        app_label = pod["metadata"].get("labels", {}).get("app", "")
        if app_label in target_labels:
            assert pod["status"]["phase"] == "Running", (
                f"Pod {pod['metadata']['name']} has phase {pod['status']['phase']}"
            )
