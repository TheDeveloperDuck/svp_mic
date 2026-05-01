#!/usr/bin/env python3
import argparse
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

INFRASTRUCTURE_DIRS = ["postgres", "redis", "kafka"]

APP_DIRS = [
    "customer-user-service",
    "planning-service",
    "expense-service",
    "frontend-service",
]

STATEFULSETS = [
    "customer-user-db",
    "planning-db",
    "expense-db",
    "redis",
    "zookeeper",
    "kafka",
]


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


def apply_dir(directory: Path) -> None:
    for manifest in sorted(directory.glob("*.yaml")):
        run(["kubectl", "apply", "-f", str(manifest)])


def helm_release_exists() -> bool:
    result = subprocess.run(
        ["helm", "status", CLUSTER_NAME, "--namespace", NAMESPACE],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def deploy_raw() -> None:
    step("Step 4/8 — Apply namespace, ConfigMap, and Secret")
    run(["kubectl", "apply", "-f", str(K8S / "namespace.yaml")])
    run(["kubectl", "apply", "-f", str(K8S / "configmap.yaml")])
    run(["kubectl", "apply", "-f", str(K8S / "secret.yaml")])

    step("Step 5/8 — Apply infrastructure (Postgres, Redis, Kafka)")
    for d in INFRASTRUCTURE_DIRS:
        apply_dir(K8S / d)

    step("Step 6/8 — Wait for infrastructure StatefulSets to be ready")
    for sts in STATEFULSETS:
        run([
            "kubectl", "rollout", "status",
            f"statefulset/{sts}",
            "-n", NAMESPACE,
            "--timeout=300s",
        ])

    step("Step 7/8 — Apply application services")
    for d in APP_DIRS:
        apply_dir(K8S / d)

    step("Step 8/8 — Show pod status")
    run(["kubectl", "get", "pods", "-n", NAMESPACE])


def deploy_helm() -> None:
    if helm_release_exists():
        step("Step 4/4 — Helm upgrade existing release")
        run(["helm", "upgrade", CLUSTER_NAME, str(HELM_CHART), "--namespace", NAMESPACE])
    else:
        step("Step 4/4 — Helm install release")
        run([
            "helm", "install", CLUSTER_NAME, str(HELM_CHART),
            "--namespace", NAMESPACE,
            "--create-namespace",
        ])

    step("Step 5/4 — Show pod status")
    run(["kubectl", "get", "pods", "-n", NAMESPACE])


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy SVP to a KinD cluster.")
    parser.add_argument(
        "--helm",
        action="store_true",
        help="Deploy using the Helm chart instead of raw manifests.",
    )
    args = parser.parse_args()

    total = 4 if args.helm else 8

    step(f"Step 1/{total} — Create KinD cluster")
    if cluster_exists():
        print(f"Cluster '{CLUSTER_NAME}' already exists, skipping creation.")
    else:
        run(["kind", "create", "cluster", "--name", CLUSTER_NAME, "--config", str(K8S / "kind-config.yaml")])

    step(f"Step 2/{total} — Build Docker images")
    for tag, dockerfile, context in IMAGES:
        run([
            "docker", "build",
            "-t", tag,
            "-f", str(PROJECT_ROOT / dockerfile),
            str(PROJECT_ROOT),
        ])

    step(f"Step 3/{total} — Load images into KinD cluster")
    for tag, _, _ in IMAGES:
        run(["kind", "load", "docker-image", tag, "--name", CLUSTER_NAME])

    if args.helm:
        deploy_helm()
    else:
        deploy_raw()


if __name__ == "__main__":
    try:
        main()
    except SystemExit as exc:
        print(f"\nDeployment failed: {exc}", file=sys.stderr)
        sys.exit(1)
