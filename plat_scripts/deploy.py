#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
K8S = PROJECT_ROOT / "k8s"
HELM_CHART = K8S / "helm" / "svp"
CLUSTER_NAME = "svp"
NAMESPACE = "svp"

IMAGES = [
    ("svp/customer-user-service:latest", "customer_user_service/Dockerfile", "customer_user_service"),
    ("svp/planning-service:latest", "planning_service/Dockerfile", "planning_service"),
    ("svp/expense-service:latest", "expense_service/Dockerfile", "expense_service"),
    ("svp/frontend-service:latest", "frontend_service/Dockerfile", "frontend_service"),
]

CALICO_MANIFEST = "https://raw.githubusercontent.com/projectcalico/calico/v3.27.3/manifests/calico.yaml"


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print(f"\n$ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, **kwargs)
    if result.returncode != 0:
        raise SystemExit(f"Command failed with exit code {result.returncode}")
    return result


def step(msg: str) -> None:
    width = 72
    print(f"\n{'=' * width}")
    print(f"  {msg}")
    print(f"{'=' * width}")


def cluster_exists() -> bool:
    result = subprocess.run(
        ["kind", "get", "clusters"],
        capture_output=True,
        text=True,
    )
    return CLUSTER_NAME in result.stdout.splitlines()


def install_calico() -> None:
    run(["kubectl", "apply", "-f", CALICO_MANIFEST])
    run([
        "kubectl", "rollout", "status",
        "daemonset/calico-node",
        "-n", "kube-system",
        "--timeout=120s",
    ])
    run([
        "kubectl", "rollout", "status",
        "deployment/calico-kube-controllers",
        "-n", "kube-system",
        "--timeout=120s",
    ])


def helm_release_exists() -> bool:
    result = subprocess.run(
        ["helm", "status", CLUSTER_NAME, "--namespace", NAMESPACE],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def deploy_helm() -> None:
    if helm_release_exists():
        step("Step 5/6 — Helm upgrade existing release")
        run(["helm", "upgrade", CLUSTER_NAME, str(HELM_CHART), "--namespace", NAMESPACE])
    else:
        step("Step 5/6 — Helm install release")
        run([
            "helm", "install", CLUSTER_NAME, str(HELM_CHART),
            "--namespace", NAMESPACE,
            "--create-namespace",
        ])

    step("Step 6/6 — Show pod status")
    run(["kubectl", "get", "pods", "-n", NAMESPACE])


def main() -> None:
    step("Step 1/6 — Create KinD cluster")
    if cluster_exists():
        print(f"Cluster '{CLUSTER_NAME}' already exists, skipping creation.")
    else:
        run(["kind", "create", "cluster", "--name", CLUSTER_NAME, "--config", str(PROJECT_ROOT / "kind-config.yaml")])

    step("Step 2/6 — Install Calico CNI")
    install_calico()

    step("Step 3/6 — Build Docker images")
    for tag, dockerfile, context in IMAGES:
        run([
            "docker", "build",
            "-t", tag,
            "-f", str(PROJECT_ROOT / dockerfile),
            str(PROJECT_ROOT),
        ])

    step("Step 4/6 — Load images into KinD cluster")
    for tag, _, _ in IMAGES:
        run(["kind", "load", "docker-image", tag, "--name", CLUSTER_NAME])

    deploy_helm()


if __name__ == "__main__":
    try:
        main()
    except SystemExit as exc:
        print(f"\nDeployment failed: {exc}", file=sys.stderr)
        sys.exit(1)
