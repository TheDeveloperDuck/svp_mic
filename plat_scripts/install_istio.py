#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
NAMESPACE = "svp"


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


def check_istioctl() -> None:
    step("Step 1/6 — Check istioctl is available")
    result = subprocess.run(
        ["istioctl", "version"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(
            "istioctl not found or not working. "
            "Install it from https://istio.io/latest/docs/setup/getting-started/ "
            "and ensure it is on PATH before running this script."
        )
    print(result.stdout.strip())
    print("istioctl is available.")


def install_istio() -> None:
    step("Step 2/6 — Install Istio (demo profile)")
    run(["istioctl", "install", "--set", "profile=demo", "-y"])


def label_namespace() -> None:
    step("Step 3/6 — Enable sidecar injection on namespace")
    run([
        "kubectl", "label", "namespace", NAMESPACE,
        "istio-injection=enabled",
        "--overwrite",
    ])


def restart_deployments() -> None:
    step("Step 4/6 — Restart deployments to inject sidecars into existing pods")
    run(["kubectl", "rollout", "restart", "deployment", "-n", NAMESPACE])


def wait_for_deployments() -> None:
    step("Step 5/6 — Wait for all deployments to be ready (timeout 300s each)")
    result = subprocess.run(
        [
            "kubectl", "get", "deployments",
            "-n", NAMESPACE,
            "-o", "jsonpath={.items[*].metadata.name}",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit("Failed to list deployments in namespace " + NAMESPACE)

    deployments = result.stdout.split()
    if not deployments:
        raise SystemExit(f"No deployments found in namespace {NAMESPACE}. Run deploy.py first.")

    print(f"Found deployments: {', '.join(deployments)}")
    for deployment in deployments:
        run([
            "kubectl", "rollout", "status",
            f"deployment/{deployment}",
            "-n", NAMESPACE,
            "--timeout=300s",
        ])


def verify_sidecars() -> None:
    step("Step 6/6 — Verify sidecar injection (all app pods must show 2/2 READY)")
    result = subprocess.run(
        ["kubectl", "get", "pods", "-n", NAMESPACE],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit("Failed to get pods in namespace " + NAMESPACE)

    output = result.stdout
    print(output)

    lines = output.strip().splitlines()
    if len(lines) <= 1:
        raise SystemExit(f"No pods found in namespace {NAMESPACE}.")

    # Parse pod lines (skip header)
    failed_pods = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 3:
            continue
        name, ready, status = parts[0], parts[1], parts[2]
        # Only check Running pods; ignore Terminating/Init/Completed
        if status != "Running":
            continue
        if ready != "2/2":
            failed_pods.append((name, ready))

    if failed_pods:
        for pod_name, pod_ready in failed_pods:
            print(f"  FAIL  {pod_name} — {pod_ready} READY (expected 2/2, sidecar missing?)")
        raise SystemExit("FAIL — one or more pods do not have the Istio sidecar injected.")

    print("PASS — all running pods have 2/2 containers (Istio sidecar present).")


def main() -> None:
    check_istioctl()
    install_istio()
    label_namespace()
    restart_deployments()
    wait_for_deployments()
    verify_sidecars()
    print("\nIstio installation and sidecar injection complete.")


if __name__ == "__main__":
    main()
