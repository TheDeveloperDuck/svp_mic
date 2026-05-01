#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ISTIO_DIR = PROJECT_ROOT / "istio-1.21.0"
ADDONS_DIR = ISTIO_DIR / "samples" / "addons"


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


def check_addons_dir() -> None:
    if not ADDONS_DIR.exists():
        raise SystemExit(
            f"Addons directory not found: {ADDONS_DIR}\n"
            "Download the Istio release and ensure istio-1.21.0/ is at the project root."
        )


def install_prometheus() -> None:
    step("Step 1/6 — Install Prometheus")
    run(["kubectl", "apply", "-f", str(ADDONS_DIR / "prometheus.yaml")])


def install_jaeger() -> None:
    step("Step 2/6 — Install Jaeger")
    run(["kubectl", "apply", "-f", str(ADDONS_DIR / "jaeger.yaml")])


def install_kiali() -> None:
    step("Step 3/6 — Install Kiali")
    run(["kubectl", "apply", "-f", str(ADDONS_DIR / "kiali.yaml")])


def install_grafana() -> None:
    step("Step 4/6 — Install Grafana")
    run(["kubectl", "apply", "-f", str(ADDONS_DIR / "grafana.yaml")])


def wait_for_deployments() -> None:
    step("Step 5/6 — Wait for all addon deployments to be ready (timeout 120s each)")
    for deployment in ("prometheus", "jaeger", "kiali", "grafana"):
        run([
            "kubectl", "rollout", "status",
            f"deployment/{deployment}",
            "-n", "istio-system",
            "--timeout=120s",
        ])


def show_pods() -> None:
    step("Step 6/6 — Show pods in istio-system")
    run(["kubectl", "get", "pods", "-n", "istio-system"])


def print_access_instructions() -> None:
    print("""
Access dashboards via kubectl port-forward:

  Kiali:
    kubectl port-forward -n istio-system svc/kiali 20001:20001
    http://localhost:20001

  Grafana:
    kubectl port-forward -n istio-system svc/grafana 3000:3000
    http://localhost:3000

  Jaeger:
    kubectl port-forward -n istio-system svc/tracing 16686:80
    http://localhost:16686

  Prometheus:
    kubectl port-forward -n istio-system svc/prometheus 9090:9090
    http://localhost:9090
""")


def main() -> None:
    check_addons_dir()
    install_prometheus()
    install_jaeger()
    install_kiali()
    install_grafana()
    wait_for_deployments()
    show_pods()
    print("\nObservability addons installed successfully.")
    print_access_instructions()


if __name__ == "__main__":
    main()
