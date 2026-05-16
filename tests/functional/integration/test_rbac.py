import json
import subprocess


def test_default_sa_cannot_create_pods():
    result = subprocess.run(
        [
            "kubectl", "auth", "can-i", "create", "pods",
            "--as=system:serviceaccount:svp:default", "-n", "svp",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert "no" in result.stdout.lower()


def test_default_sa_cannot_delete_pods():
    result = subprocess.run(
        [
            "kubectl", "auth", "can-i", "delete", "pods",
            "--as=system:serviceaccount:svp:default", "-n", "svp",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert "no" in result.stdout.lower()


def test_default_sa_cannot_get_secrets():
    result = subprocess.run(
        [
            "kubectl", "auth", "can-i", "get", "secrets",
            "--as=system:serviceaccount:svp:default", "-n", "svp",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert "no" in result.stdout.lower()


def test_no_cluster_admin_binding_in_svp():
    result = subprocess.run(
        ["kubectl", "get", "clusterrolebinding", "-o", "json"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0
    bindings = json.loads(result.stdout)["items"]
    for binding in bindings:
        if binding.get("roleRef", {}).get("name") == "cluster-admin":
            subjects = binding.get("subjects") or []
            for subject in subjects:
                assert subject.get("namespace") != "svp", (
                    f"cluster-admin binding found for subject in svp namespace: {subject}"
                )
