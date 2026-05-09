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
    step("Step 1/9 — Check istioctl is available")
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
    step("Step 2/9 — Install Istio (demo profile)")
    run(["istioctl", "install", "--set", "profile=demo", "-y"])


def verify_istio_system() -> None:
    step("Step 3/9 — Verify istiod is ready in istio-system")
    run([
        "kubectl", "rollout", "status",
        "deployment/istiod",
        "-n", "istio-system",
        "--timeout=120s",
    ])


def label_namespace() -> None:
    step("Step 4/9 — Enable sidecar injection on namespace")
    run([
        "kubectl", "label", "namespace", NAMESPACE,
        "istio-injection=enabled",
        "--overwrite",
    ])


def restart_deployments() -> None:
    step("Step 5/9 — Restart deployments to inject sidecars into existing pods")
    run(["kubectl", "rollout", "restart", "deployment", "-n", NAMESPACE])


def wait_for_deployments() -> None:
    step("Step 6/9 — Wait for all deployments to be ready (timeout 300s each)")
    result = subprocess.run(
        ["kubectl", "get", "deployments", "-n", NAMESPACE, "-o", "name"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit("Failed to list deployments in namespace " + NAMESPACE)

    # Each line is already in "deployment/<name>" form
    deployments = result.stdout.strip().splitlines()
    if not deployments:
        raise SystemExit(f"No deployments found in namespace {NAMESPACE}. Run deploy.py first.")

    print(f"Found deployments: {', '.join(deployments)}")
    for deployment in deployments:
        run([
            "kubectl", "rollout", "status",
            deployment,
            "-n", NAMESPACE,
            "--timeout=300s",
        ])


def verify_sidecars() -> None:
    step("Step 7/9 — Verify sidecar injection (all app pods must show 2/2 READY)")
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

    failed_pods = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 3:
            continue
        name, ready, status = parts[0], parts[1], parts[2]
        # Only check Deployment pods (svp-* prefix); skip StatefulSet pods
        if not name.startswith("svp-"):
            continue
        if status != "Running":
            continue
        if ready != "2/2":
            failed_pods.append((name, ready))

    if failed_pods:
        for pod_name, pod_ready in failed_pods:
            print(f"  FAIL  {pod_name} — {pod_ready} READY (expected 2/2, sidecar missing?)")
        print("\nSIDECAR INJECTION FAILED")
        raise SystemExit(1)

    print("SIDECAR INJECTION VERIFIED")


def apply_istio_policies() -> None:
    step("Step 8/9 — Apply mTLS and authorisation policies")
    istio_dir = PROJECT_ROOT / "k8s" / "istio"
    run(["kubectl", "apply", "-f", str(istio_dir / "security" / "peer-authentication.yaml")])
    run(["kubectl", "apply", "-f", str(istio_dir / "security")])
    run(["kubectl", "apply", "-f", str(istio_dir / "telemetry.yaml")])
    run(["kubectl", "get", "peerauthentication", "-n", NAMESPACE])
    run(["kubectl", "get", "authorizationpolicy", "-n", NAMESPACE])
    run(["kubectl", "get", "telemetry", "-n", NAMESPACE])


def apply_istio_networking() -> None:
    step("Step 9/9 — Apply ingress gateway, virtual services, and destination rules")
    istio_dir = PROJECT_ROOT / "k8s" / "istio"
    run(["kubectl", "apply", "-f", str(istio_dir / "gateway.yaml")])
    run(["kubectl", "apply", "-f", str(istio_dir / "virtual-services.yaml")])
    run(["kubectl", "apply", "-f", str(istio_dir / "destination-rules.yaml")])
    run(["kubectl", "get", "gateway", "-n", NAMESPACE])
    run(["kubectl", "get", "virtualservice", "-n", NAMESPACE])
    run(["kubectl", "get", "destinationrule", "-n", NAMESPACE])


def main() -> None:
    check_istioctl()
    install_istio()
    verify_istio_system()
    label_namespace()
    restart_deployments()
    wait_for_deployments()
    verify_sidecars()
    apply_istio_policies()
    apply_istio_networking()
    print("\nIstio installation, sidecar injection, and networking setup complete.")


if __name__ == "__main__":
    main()
