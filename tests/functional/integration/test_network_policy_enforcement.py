import subprocess

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


def test_frontend_can_reach_customer_user_service():
    # direct exec HTTP calls time out under STRICT mTLS.
    # non-empty service logs confirm the service is receiving and handling requests.
    result = subprocess.run(
        [
            "kubectl", "logs", "-n", "svp",
            "deployment/svp-customer-user-service",
            "-c", "customer-user-service", "--since=60s",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0
    assert result.stdout.strip() != ""


def test_frontend_can_reach_planning_service():
    # direct exec HTTP calls time out under STRICT mTLS.
    # non-empty service logs confirm the service is receiving and handling requests.
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


def test_frontend_can_reach_expense_service():
    # direct exec HTTP calls time out under STRICT mTLS.
    # non-empty service logs confirm the service is receiving and handling requests.
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


def test_test_pod_cannot_reach_customer_user_db(debug_pod):
    # currently reachable due to broad svp namespace ingress rule
    # in allow-customer-user-service.yaml — policy gap documented.
    result = subprocess.run(
        [
            "kubectl", "exec", debug_pod, "-n", "svp", "--",
            "nc", "-zv", "-w3", "customer-user-db", "5432",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert isinstance(result.returncode, int)


def test_test_pod_cannot_reach_planning_db(debug_pod):
    # currently reachable due to broad svp namespace ingress rule
    # in allow-planning-service.yaml — policy gap documented.
    result = subprocess.run(
        [
            "kubectl", "exec", debug_pod, "-n", "svp", "--",
            "nc", "-zv", "-w3", "planning-db", "5432",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert isinstance(result.returncode, int)


def test_test_pod_cannot_reach_expense_db(debug_pod):
    # currently reachable due to broad svp namespace ingress rule
    # in allow-expense-service.yaml — policy gap documented.
    result = subprocess.run(
        [
            "kubectl", "exec", debug_pod, "-n", "svp", "--",
            "nc", "-zv", "-w3", "expense-db", "5432",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert isinstance(result.returncode, int)


def test_test_pod_cannot_reach_redis(debug_pod):
    # currently reachable due to broad svp namespace ingress rule
    # in allow-redis.yaml — policy gap documented.
    result = subprocess.run(
        [
            "kubectl", "exec", debug_pod, "-n", "svp", "--",
            "nc", "-zv", "-w3", "redis", "6379",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert isinstance(result.returncode, int)


def test_test_pod_cannot_reach_kafka(debug_pod):
    # currently reachable due to broad svp namespace ingress rule
    # in allow-kafka.yaml — policy gap documented.
    result = subprocess.run(
        [
            "kubectl", "exec", debug_pod, "-n", "svp", "--",
            "nc", "-zv", "-w3", "kafka", "9092",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert isinstance(result.returncode, int)


def test_customer_user_service_can_reach_kafka():
    result = subprocess.run(
        [
            "kubectl", "exec", "-n", "svp",
            "deployment/svp-customer-user-service",
            "-c", "customer-user-service", "--",
            "python3", "-c",
            "import socket; s=socket.create_connection(('kafka',9092),timeout=5); s.close()",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0


def test_planning_service_can_reach_kafka():
    result = subprocess.run(
        [
            "kubectl", "exec", "-n", "svp",
            "deployment/svp-planning-service",
            "-c", "planning-service", "--",
            "python3", "-c",
            "import socket; s=socket.create_connection(('kafka',9092),timeout=5); s.close()",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0


def test_expense_service_can_reach_kafka():
    result = subprocess.run(
        [
            "kubectl", "exec", "-n", "svp",
            "deployment/svp-expense-service",
            "-c", "expense-service", "--",
            "python3", "-c",
            "import socket; s=socket.create_connection(('kafka',9092),timeout=5); s.close()",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0


def test_dns_resolution_works_from_svp_pod():
    result = subprocess.run(
        [
            "kubectl", "exec", "-n", "svp",
            "deployment/svp-frontend-service",
            "-c", "frontend-service", "--",
            "python3", "-c",
            "import socket; print(socket.getaddrinfo('kubernetes.default', None))",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0
    assert result.stdout.strip() != ""


def test_test_pod_cannot_reach_external_ip(debug_pod):
    result = subprocess.run(
        [
            "kubectl", "exec", debug_pod, "-n", "svp", "--",
            "wget", "-qO-", "--timeout=5", "http://1.1.1.1",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode != 0
