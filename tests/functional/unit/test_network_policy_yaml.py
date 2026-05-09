import re
from pathlib import Path

import yaml

_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
_NP_DIR = _PROJECT_ROOT / "k8s" / "helm" / "svp" / "templates" / "network-policies"


def _load(filename: str) -> dict:
    text = (_NP_DIR / filename).read_text()
    text = re.sub(r"\{\{[^}]+\}\}", "PLACEHOLDER", text)
    return yaml.safe_load(text)


def _load_all(filename: str) -> list:
    text = (_NP_DIR / filename).read_text()
    text = re.sub(r"\{\{[^}]+\}\}", "PLACEHOLDER", text)
    return [d for d in yaml.safe_load_all(text) if d]


def _raw(filename: str) -> str:
    return (_NP_DIR / filename).read_text()


def _all_egress_ports(docs: list) -> list:
    ports = []
    for doc in docs:
        for rule in doc.get("spec", {}).get("egress") or []:
            ports.extend(rule.get("ports") or [])
    return ports


def _all_ingress_ports(docs: list) -> list:
    ports = []
    for doc in docs:
        for rule in doc.get("spec", {}).get("ingress") or []:
            ports.extend(rule.get("ports") or [])
    return ports


def _all_from_entries(docs: list) -> list:
    entries = []
    for doc in docs:
        for rule in doc.get("spec", {}).get("ingress") or []:
            entries.extend(rule.get("from") or [])
    return entries


def _all_egress_from_entries(docs: list) -> list:
    entries = []
    for doc in docs:
        for rule in doc.get("spec", {}).get("egress") or []:
            entries.extend(rule.get("to") or [])
    return entries


def _find_doc(docs: list, name: str) -> dict:
    return next(d for d in docs if d.get("metadata", {}).get("name") == name)


# ---------------------------------------------------------------------------
# default-deny.yaml
# ---------------------------------------------------------------------------

def test_default_deny_parses():
    _load("default-deny.yaml")


def test_default_deny_policy_types():
    doc = _load("default-deny.yaml")
    types = doc["spec"]["policyTypes"]
    assert "Ingress" in types
    assert "Egress" in types


def test_default_deny_empty_pod_selector():
    doc = _load("default-deny.yaml")
    selector = doc["spec"]["podSelector"]
    assert selector == {} or not selector.get("matchLabels")


def test_default_deny_no_ingress_rules():
    doc = _load("default-deny.yaml")
    ingress = doc["spec"].get("ingress")
    assert not ingress


def test_default_deny_no_egress_rules():
    doc = _load("default-deny.yaml")
    egress = doc["spec"].get("egress")
    assert not egress


# ---------------------------------------------------------------------------
# allow-dns.yaml
# ---------------------------------------------------------------------------

def test_allow_dns_parses():
    _load("allow-dns.yaml")


def test_allow_dns_egress_port_53_udp():
    docs = _load_all("allow-dns.yaml")
    ports = _all_egress_ports(docs)
    assert any(p.get("port") == 53 and p.get("protocol") == "UDP" for p in ports)


def test_allow_dns_egress_port_53_tcp():
    docs = _load_all("allow-dns.yaml")
    ports = _all_egress_ports(docs)
    assert any(p.get("port") == 53 and p.get("protocol") == "TCP" for p in ports)


def test_allow_dns_namespace_selector_kube_system():
    docs = _load_all("allow-dns.yaml")
    to_entries = _all_egress_from_entries(docs)
    assert any(
        entry.get("namespaceSelector", {})
        .get("matchLabels", {})
        .get("kubernetes.io/metadata.name") == "kube-system"
        for entry in to_entries
    )


# ---------------------------------------------------------------------------
# allow-customer-user-service.yaml
# ---------------------------------------------------------------------------

def test_allow_customer_user_service_parses():
    _load_all("allow-customer-user-service.yaml")


def test_allow_customer_user_service_ingress_has_two_from_entries():
    docs = _load_all("allow-customer-user-service.yaml")
    doc = _find_doc(docs, "allow-customer-user-service-ingress")
    assert len(doc["spec"]["ingress"]) == 2


def test_allow_customer_user_service_ingress_from_svp_namespace():
    docs = _load_all("allow-customer-user-service.yaml")
    doc = _find_doc(docs, "allow-customer-user-service-ingress")
    froms = _all_from_entries([doc])
    assert any("podSelector" in entry for entry in froms)


def test_allow_customer_user_service_ingress_from_istio_system():
    docs = _load_all("allow-customer-user-service.yaml")
    doc = _find_doc(docs, "allow-customer-user-service-ingress")
    froms = _all_from_entries([doc])
    assert any(
        entry.get("namespaceSelector", {})
        .get("matchLabels", {})
        .get("kubernetes.io/metadata.name") == "istio-system"
        for entry in froms
    )


def test_allow_customer_user_service_istio_system_from_has_no_pod_selector():
    docs = _load_all("allow-customer-user-service.yaml")
    doc = _find_doc(docs, "allow-customer-user-service-ingress")
    froms = _all_from_entries([doc])
    istio_entry = next(
        e for e in froms
        if e.get("namespaceSelector", {}).get("matchLabels", {}).get("kubernetes.io/metadata.name") == "istio-system"
    )
    assert "podSelector" not in istio_entry


def test_allow_customer_user_service_no_istio_ingress_namespace_reference():
    assert "istio-ingress" not in _raw("allow-customer-user-service.yaml")


def test_allow_customer_user_service_egress_port_5432():
    docs = _load_all("allow-customer-user-service.yaml")
    doc = _find_doc(docs, "allow-customer-user-service-egress")
    ports = _all_egress_ports([doc])
    assert any(p.get("port") == 5432 for p in ports)


def test_allow_customer_user_service_egress_port_6379():
    docs = _load_all("allow-customer-user-service.yaml")
    doc = _find_doc(docs, "allow-customer-user-service-egress")
    ports = _all_egress_ports([doc])
    assert any(p.get("port") == 6379 for p in ports)


def test_allow_customer_user_service_egress_port_9092():
    docs = _load_all("allow-customer-user-service.yaml")
    doc = _find_doc(docs, "allow-customer-user-service-egress")
    ports = _all_egress_ports([doc])
    assert any(p.get("port") == 9092 for p in ports)


# ---------------------------------------------------------------------------
# allow-planning-service.yaml
# ---------------------------------------------------------------------------

def test_allow_planning_service_parses():
    _load_all("allow-planning-service.yaml")


def test_allow_planning_service_ingress_has_two_from_entries():
    docs = _load_all("allow-planning-service.yaml")
    doc = _find_doc(docs, "allow-planning-service-ingress")
    assert len(doc["spec"]["ingress"]) == 2


def test_allow_planning_service_ingress_from_svp_namespace():
    docs = _load_all("allow-planning-service.yaml")
    doc = _find_doc(docs, "allow-planning-service-ingress")
    froms = _all_from_entries([doc])
    assert any("podSelector" in entry for entry in froms)


def test_allow_planning_service_ingress_from_istio_system():
    docs = _load_all("allow-planning-service.yaml")
    doc = _find_doc(docs, "allow-planning-service-ingress")
    froms = _all_from_entries([doc])
    assert any(
        entry.get("namespaceSelector", {})
        .get("matchLabels", {})
        .get("kubernetes.io/metadata.name") == "istio-system"
        for entry in froms
    )


def test_allow_planning_service_istio_system_from_has_no_pod_selector():
    docs = _load_all("allow-planning-service.yaml")
    doc = _find_doc(docs, "allow-planning-service-ingress")
    froms = _all_from_entries([doc])
    istio_entry = next(
        e for e in froms
        if e.get("namespaceSelector", {}).get("matchLabels", {}).get("kubernetes.io/metadata.name") == "istio-system"
    )
    assert "podSelector" not in istio_entry


def test_allow_planning_service_no_istio_ingress_namespace_reference():
    assert "istio-ingress" not in _raw("allow-planning-service.yaml")


def test_allow_planning_service_egress_port_5432():
    docs = _load_all("allow-planning-service.yaml")
    doc = _find_doc(docs, "allow-planning-service-egress")
    ports = _all_egress_ports([doc])
    assert any(p.get("port") == 5432 for p in ports)


def test_allow_planning_service_egress_port_9092():
    docs = _load_all("allow-planning-service.yaml")
    doc = _find_doc(docs, "allow-planning-service-egress")
    ports = _all_egress_ports([doc])
    assert any(p.get("port") == 9092 for p in ports)


# ---------------------------------------------------------------------------
# allow-expense-service.yaml
# ---------------------------------------------------------------------------

def test_allow_expense_service_parses():
    _load_all("allow-expense-service.yaml")


def test_allow_expense_service_ingress_has_two_from_entries():
    docs = _load_all("allow-expense-service.yaml")
    doc = _find_doc(docs, "allow-expense-service-ingress")
    assert len(doc["spec"]["ingress"]) == 2


def test_allow_expense_service_ingress_from_svp_namespace():
    docs = _load_all("allow-expense-service.yaml")
    doc = _find_doc(docs, "allow-expense-service-ingress")
    froms = _all_from_entries([doc])
    assert any("podSelector" in entry for entry in froms)


def test_allow_expense_service_ingress_from_istio_system():
    docs = _load_all("allow-expense-service.yaml")
    doc = _find_doc(docs, "allow-expense-service-ingress")
    froms = _all_from_entries([doc])
    assert any(
        entry.get("namespaceSelector", {})
        .get("matchLabels", {})
        .get("kubernetes.io/metadata.name") == "istio-system"
        for entry in froms
    )


def test_allow_expense_service_istio_system_from_has_no_pod_selector():
    docs = _load_all("allow-expense-service.yaml")
    doc = _find_doc(docs, "allow-expense-service-ingress")
    froms = _all_from_entries([doc])
    istio_entry = next(
        e for e in froms
        if e.get("namespaceSelector", {}).get("matchLabels", {}).get("kubernetes.io/metadata.name") == "istio-system"
    )
    assert "podSelector" not in istio_entry


def test_allow_expense_service_no_istio_ingress_namespace_reference():
    assert "istio-ingress" not in _raw("allow-expense-service.yaml")


def test_allow_expense_service_egress_port_5432():
    docs = _load_all("allow-expense-service.yaml")
    doc = _find_doc(docs, "allow-expense-service-egress")
    ports = _all_egress_ports([doc])
    assert any(p.get("port") == 5432 for p in ports)


def test_allow_expense_service_egress_port_9092():
    docs = _load_all("allow-expense-service.yaml")
    doc = _find_doc(docs, "allow-expense-service-egress")
    ports = _all_egress_ports([doc])
    assert any(p.get("port") == 9092 for p in ports)


# ---------------------------------------------------------------------------
# allow-frontend-service.yaml
# ---------------------------------------------------------------------------

def test_allow_frontend_service_parses():
    _load_all("allow-frontend-service.yaml")


def test_allow_frontend_service_ingress_has_one_from_entry():
    docs = _load_all("allow-frontend-service.yaml")
    doc = _find_doc(docs, "allow-frontend-service-ingress")
    assert len(doc["spec"]["ingress"]) == 1


def test_allow_frontend_service_ingress_from_istio_system():
    docs = _load_all("allow-frontend-service.yaml")
    doc = _find_doc(docs, "allow-frontend-service-ingress")
    froms = _all_from_entries([doc])
    assert any(
        entry.get("namespaceSelector", {})
        .get("matchLabels", {})
        .get("kubernetes.io/metadata.name") == "istio-system"
        for entry in froms
    )


def test_allow_frontend_service_istio_system_from_has_no_pod_selector():
    docs = _load_all("allow-frontend-service.yaml")
    doc = _find_doc(docs, "allow-frontend-service-ingress")
    froms = _all_from_entries([doc])
    istio_entry = next(
        e for e in froms
        if e.get("namespaceSelector", {}).get("matchLabels", {}).get("kubernetes.io/metadata.name") == "istio-system"
    )
    assert "podSelector" not in istio_entry


def test_allow_frontend_service_egress_port_8001():
    docs = _load_all("allow-frontend-service.yaml")
    doc = _find_doc(docs, "allow-frontend-service-egress")
    ports = _all_egress_ports([doc])
    assert any(p.get("port") == 8001 for p in ports)


def test_allow_frontend_service_egress_port_8002():
    docs = _load_all("allow-frontend-service.yaml")
    doc = _find_doc(docs, "allow-frontend-service-egress")
    ports = _all_egress_ports([doc])
    assert any(p.get("port") == 8002 for p in ports)


def test_allow_frontend_service_egress_port_8003():
    docs = _load_all("allow-frontend-service.yaml")
    doc = _find_doc(docs, "allow-frontend-service-egress")
    ports = _all_egress_ports([doc])
    assert any(p.get("port") == 8003 for p in ports)


# ---------------------------------------------------------------------------
# allow-kafka.yaml
# ---------------------------------------------------------------------------

def test_allow_kafka_parses():
    _load_all("allow-kafka.yaml")


def test_allow_kafka_ingress_allows_customer_user_service():
    docs = _load_all("allow-kafka.yaml")
    doc = _find_doc(docs, "allow-kafka-ingress")
    froms = _all_from_entries([doc])
    assert any(
        entry.get("podSelector", {}).get("matchLabels", {}).get("app") == "customer-user-service"
        for entry in froms
    )


def test_allow_kafka_ingress_allows_planning_service():
    docs = _load_all("allow-kafka.yaml")
    doc = _find_doc(docs, "allow-kafka-ingress")
    froms = _all_from_entries([doc])
    assert any(
        entry.get("podSelector", {}).get("matchLabels", {}).get("app") == "planning-service"
        for entry in froms
    )


def test_allow_kafka_ingress_allows_expense_service():
    docs = _load_all("allow-kafka.yaml")
    doc = _find_doc(docs, "allow-kafka-ingress")
    froms = _all_from_entries([doc])
    assert any(
        entry.get("podSelector", {}).get("matchLabels", {}).get("app") == "expense-service"
        for entry in froms
    )


def test_allow_kafka_egress_to_zookeeper_port_2181():
    docs = _load_all("allow-kafka.yaml")
    doc = _find_doc(docs, "allow-kafka-egress")
    ports = _all_egress_ports([doc])
    assert any(p.get("port") == 2181 for p in ports)


def test_allow_kafka_egress_to_kafka_port_9092():
    docs = _load_all("allow-kafka.yaml")
    doc = _find_doc(docs, "allow-zookeeper-egress")
    ports = _all_egress_ports([doc])
    assert any(p.get("port") == 9092 for p in ports)


# ---------------------------------------------------------------------------
# allow-redis.yaml
# ---------------------------------------------------------------------------

def test_allow_redis_parses():
    _load("allow-redis.yaml")


def test_allow_redis_ingress_allows_only_customer_user_service():
    docs = _load_all("allow-redis.yaml")
    doc = docs[0]
    ingress_rules = doc["spec"]["ingress"]
    assert len(ingress_rules) == 1
    froms = ingress_rules[0].get("from", [])
    assert len(froms) == 1
    assert froms[0].get("podSelector", {}).get("matchLabels", {}).get("app") == "customer-user-service"


# ---------------------------------------------------------------------------
# allow-istio-controlplane.yaml
# ---------------------------------------------------------------------------

def test_allow_istio_controlplane_parses():
    _load_all("allow-istio-controlplane.yaml")


def test_allow_istio_controlplane_egress_port_15012():
    docs = _load_all("allow-istio-controlplane.yaml")
    doc = _find_doc(docs, "allow-istiod-egress")
    ports = _all_egress_ports([doc])
    assert any(p.get("port") == 15012 for p in ports)


def test_allow_istio_controlplane_egress_port_15010():
    docs = _load_all("allow-istio-controlplane.yaml")
    doc = _find_doc(docs, "allow-istiod-egress")
    ports = _all_egress_ports([doc])
    assert any(p.get("port") == 15010 for p in ports)


def test_allow_istio_controlplane_egress_port_15014():
    docs = _load_all("allow-istio-controlplane.yaml")
    doc = _find_doc(docs, "allow-istiod-egress")
    ports = _all_egress_ports([doc])
    assert any(p.get("port") == 15014 for p in ports)


def test_allow_istio_controlplane_ingress_from_istio_system_port_15020():
    docs = _load_all("allow-istio-controlplane.yaml")
    doc = _find_doc(docs, "allow-istio-healthcheck-ingress")
    ports = _all_ingress_ports([doc])
    assert any(p.get("port") == 15020 for p in ports)


def test_allow_istio_controlplane_ingress_from_istio_system_port_15021():
    docs = _load_all("allow-istio-controlplane.yaml")
    doc = _find_doc(docs, "allow-istio-healthcheck-ingress")
    ports = _all_ingress_ports([doc])
    assert any(p.get("port") == 15021 for p in ports)
