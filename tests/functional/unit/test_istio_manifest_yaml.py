from pathlib import Path

import yaml

_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
_ISTIO_DIR = _PROJECT_ROOT / "k8s" / "istio"
_SEC_DIR = _ISTIO_DIR / "security"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _load_all(path: Path) -> list:
    return [d for d in yaml.safe_load_all(path.read_text()) if d]


def _all_principals(doc: dict) -> list:
    principals = []
    for rule in doc.get("spec", {}).get("rules") or []:
        for frm in rule.get("from") or []:
            principals.extend(frm.get("source", {}).get("principals") or [])
    return principals


# ---------------------------------------------------------------------------
# peer-authentication.yaml
# ---------------------------------------------------------------------------

def test_peer_authentication_parses():
    _load(_SEC_DIR / "peer-authentication.yaml")


def test_peer_authentication_mtls_mode_strict():
    doc = _load(_SEC_DIR / "peer-authentication.yaml")
    assert doc["spec"]["mtls"]["mode"] == "STRICT"


def test_peer_authentication_no_workload_selector():
    doc = _load(_SEC_DIR / "peer-authentication.yaml")
    assert "workloadSelector" not in doc.get("spec", {})


def test_peer_authentication_namespace_svp():
    doc = _load(_SEC_DIR / "peer-authentication.yaml")
    assert doc["metadata"]["namespace"] == "svp"


# ---------------------------------------------------------------------------
# allow-customer-user-service (AuthorizationPolicy)
# ---------------------------------------------------------------------------

def test_authz_customer_user_service_parses():
    _load(_SEC_DIR / "allow-customer-user-service.yaml")


def test_authz_customer_user_service_action_allow():
    doc = _load(_SEC_DIR / "allow-customer-user-service.yaml")
    assert doc["spec"]["action"] == "ALLOW"


def test_authz_customer_user_service_exactly_two_source_principals():
    doc = _load(_SEC_DIR / "allow-customer-user-service.yaml")
    assert len(_all_principals(doc)) == 2


def test_authz_customer_user_service_svp_default_principal_present():
    doc = _load(_SEC_DIR / "allow-customer-user-service.yaml")
    principals = _all_principals(doc)
    assert any("cluster.local/ns/svp/sa/default" in p for p in principals)


def test_authz_customer_user_service_ingressgateway_principal_present():
    doc = _load(_SEC_DIR / "allow-customer-user-service.yaml")
    principals = _all_principals(doc)
    assert any("istio-ingressgateway" in p for p in principals)


# ---------------------------------------------------------------------------
# allow-planning-service (AuthorizationPolicy)
# ---------------------------------------------------------------------------

def test_authz_planning_service_parses():
    _load(_SEC_DIR / "allow-planning-service.yaml")


def test_authz_planning_service_action_allow():
    doc = _load(_SEC_DIR / "allow-planning-service.yaml")
    assert doc["spec"]["action"] == "ALLOW"


def test_authz_planning_service_exactly_two_source_principals():
    doc = _load(_SEC_DIR / "allow-planning-service.yaml")
    assert len(_all_principals(doc)) == 2


# ---------------------------------------------------------------------------
# allow-expense-service (AuthorizationPolicy)
# ---------------------------------------------------------------------------

def test_authz_expense_service_parses():
    _load(_SEC_DIR / "allow-expense-service.yaml")


def test_authz_expense_service_action_allow():
    doc = _load(_SEC_DIR / "allow-expense-service.yaml")
    assert doc["spec"]["action"] == "ALLOW"


def test_authz_expense_service_exactly_two_source_principals():
    doc = _load(_SEC_DIR / "allow-expense-service.yaml")
    assert len(_all_principals(doc)) == 2


# ---------------------------------------------------------------------------
# allow-frontend-service (AuthorizationPolicy)
# ---------------------------------------------------------------------------

def test_authz_frontend_service_parses():
    _load(_SEC_DIR / "allow-frontend-service.yaml")


def test_authz_frontend_service_action_allow():
    doc = _load(_SEC_DIR / "allow-frontend-service.yaml")
    assert doc["spec"]["action"] == "ALLOW"


def test_authz_frontend_service_exactly_one_source_principal():
    doc = _load(_SEC_DIR / "allow-frontend-service.yaml")
    assert len(_all_principals(doc)) == 1


def test_authz_frontend_service_source_principal_is_ingressgateway():
    doc = _load(_SEC_DIR / "allow-frontend-service.yaml")
    principals = _all_principals(doc)
    assert any("istio-ingressgateway" in p for p in principals)


# ---------------------------------------------------------------------------
# allow-ingress-gateway (AuthorizationPolicy)
# ---------------------------------------------------------------------------

def test_authz_ingress_gateway_parses():
    _load(_SEC_DIR / "allow-ingress-gateway.yaml")


def test_authz_ingress_gateway_action_allow():
    doc = _load(_SEC_DIR / "allow-ingress-gateway.yaml")
    assert doc["spec"]["action"] == "ALLOW"


def test_authz_ingress_gateway_empty_rule_allows_all():
    doc = _load(_SEC_DIR / "allow-ingress-gateway.yaml")
    rules = doc["spec"]["rules"]
    assert any(rule == {} or rule is None for rule in rules)


def test_authz_ingress_gateway_namespace_istio_system():
    doc = _load(_SEC_DIR / "allow-ingress-gateway.yaml")
    assert doc["metadata"]["namespace"] == "istio-system"


# ---------------------------------------------------------------------------
# telemetry.yaml
# ---------------------------------------------------------------------------

def test_telemetry_parses():
    _load(_ISTIO_DIR / "telemetry.yaml")


def test_telemetry_sampling_100():
    doc = _load(_ISTIO_DIR / "telemetry.yaml")
    tracing = doc["spec"]["tracing"]
    assert any(entry.get("randomSamplingPercentage") == 100.0 for entry in tracing)


def test_telemetry_namespace_svp():
    doc = _load(_ISTIO_DIR / "telemetry.yaml")
    assert doc["metadata"]["namespace"] == "svp"


# ---------------------------------------------------------------------------
# destination-rules.yaml
# ---------------------------------------------------------------------------

def _dr_for(docs: list, host: str) -> dict:
    return next(d for d in docs if d.get("spec", {}).get("host") == host)


def test_destination_rule_customer_user_service_round_robin():
    docs = _load_all(_ISTIO_DIR / "destination-rules.yaml")
    dr = _dr_for(docs, "customer-user-service")
    assert dr["spec"]["trafficPolicy"]["loadBalancer"]["simple"] == "ROUND_ROBIN"


def test_destination_rule_planning_service_round_robin():
    docs = _load_all(_ISTIO_DIR / "destination-rules.yaml")
    dr = _dr_for(docs, "planning-service")
    assert dr["spec"]["trafficPolicy"]["loadBalancer"]["simple"] == "ROUND_ROBIN"


def test_destination_rule_expense_service_round_robin():
    docs = _load_all(_ISTIO_DIR / "destination-rules.yaml")
    dr = _dr_for(docs, "expense-service")
    assert dr["spec"]["trafficPolicy"]["loadBalancer"]["simple"] == "ROUND_ROBIN"


def test_destination_rule_frontend_service_round_robin():
    docs = _load_all(_ISTIO_DIR / "destination-rules.yaml")
    dr = _dr_for(docs, "frontend-service")
    assert dr["spec"]["trafficPolicy"]["loadBalancer"]["simple"] == "ROUND_ROBIN"


def test_destination_rule_customer_user_service_max_requests_per_connection_10():
    docs = _load_all(_ISTIO_DIR / "destination-rules.yaml")
    dr = _dr_for(docs, "customer-user-service")
    assert dr["spec"]["trafficPolicy"]["connectionPool"]["http"]["maxRequestsPerConnection"] == 10


def test_destination_rule_customer_user_service_connect_timeout_30s():
    docs = _load_all(_ISTIO_DIR / "destination-rules.yaml")
    dr = _dr_for(docs, "customer-user-service")
    assert dr["spec"]["trafficPolicy"]["connectionPool"]["tcp"]["connectTimeout"] == "30s"


def test_destination_rule_customer_user_service_consecutive_5xx_errors_5():
    docs = _load_all(_ISTIO_DIR / "destination-rules.yaml")
    dr = _dr_for(docs, "customer-user-service")
    assert dr["spec"]["trafficPolicy"]["outlierDetection"]["consecutive5xxErrors"] == 5


def test_destination_rule_customer_user_service_base_ejection_time_30s():
    docs = _load_all(_ISTIO_DIR / "destination-rules.yaml")
    dr = _dr_for(docs, "customer-user-service")
    assert dr["spec"]["trafficPolicy"]["outlierDetection"]["baseEjectionTime"] == "30s"


def test_destination_rule_planning_service_correct_connection_pool_settings():
    docs = _load_all(_ISTIO_DIR / "destination-rules.yaml")
    dr = _dr_for(docs, "planning-service")
    pool = dr["spec"]["trafficPolicy"]["connectionPool"]
    assert pool["http"]["maxRequestsPerConnection"] == 10
    assert pool["tcp"]["connectTimeout"] == "30s"


def test_destination_rule_planning_service_correct_outlier_detection_settings():
    docs = _load_all(_ISTIO_DIR / "destination-rules.yaml")
    dr = _dr_for(docs, "planning-service")
    od = dr["spec"]["trafficPolicy"]["outlierDetection"]
    assert od["consecutive5xxErrors"] == 5
    assert od["baseEjectionTime"] == "30s"


def test_destination_rule_expense_service_correct_connection_pool_settings():
    docs = _load_all(_ISTIO_DIR / "destination-rules.yaml")
    dr = _dr_for(docs, "expense-service")
    pool = dr["spec"]["trafficPolicy"]["connectionPool"]
    assert pool["http"]["maxRequestsPerConnection"] == 10
    assert pool["tcp"]["connectTimeout"] == "30s"


def test_destination_rule_expense_service_correct_outlier_detection_settings():
    docs = _load_all(_ISTIO_DIR / "destination-rules.yaml")
    dr = _dr_for(docs, "expense-service")
    od = dr["spec"]["trafficPolicy"]["outlierDetection"]
    assert od["consecutive5xxErrors"] == 5
    assert od["baseEjectionTime"] == "30s"


def test_destination_rule_frontend_service_correct_connection_pool_settings():
    docs = _load_all(_ISTIO_DIR / "destination-rules.yaml")
    dr = _dr_for(docs, "frontend-service")
    pool = dr["spec"]["trafficPolicy"]["connectionPool"]
    assert pool["http"]["maxRequestsPerConnection"] == 10
    assert pool["tcp"]["connectTimeout"] == "30s"


def test_destination_rule_frontend_service_correct_outlier_detection_settings():
    docs = _load_all(_ISTIO_DIR / "destination-rules.yaml")
    dr = _dr_for(docs, "frontend-service")
    od = dr["spec"]["trafficPolicy"]["outlierDetection"]
    assert od["consecutive5xxErrors"] == 5
    assert od["baseEjectionTime"] == "30s"


# ---------------------------------------------------------------------------
# gateway.yaml
# ---------------------------------------------------------------------------

def test_gateway_parses():
    _load(_ISTIO_DIR / "gateway.yaml")


def test_gateway_port_80_http():
    doc = _load(_ISTIO_DIR / "gateway.yaml")
    servers = doc["spec"]["servers"]
    assert any(
        s.get("port", {}).get("number") == 80 and s.get("port", {}).get("protocol") == "HTTP"
        for s in servers
    )


def test_gateway_selector_ingressgateway():
    doc = _load(_ISTIO_DIR / "gateway.yaml")
    assert doc["spec"]["selector"]["istio"] == "ingressgateway"


def test_gateway_hosts_wildcard():
    doc = _load(_ISTIO_DIR / "gateway.yaml")
    hosts = doc["spec"]["servers"][0]["hosts"]
    assert "*" in hosts


# ---------------------------------------------------------------------------
# virtual-services.yaml
# ---------------------------------------------------------------------------

def _vs_for(docs: list, name: str) -> dict:
    return next(d for d in docs if d.get("metadata", {}).get("name") == name)


def _all_uri_prefixes(vs: dict) -> list:
    prefixes = []
    for http_rule in vs.get("spec", {}).get("http") or []:
        for match in http_rule.get("match") or []:
            prefix = match.get("uri", {}).get("prefix")
            if prefix is not None:
                prefixes.append(prefix)
    return prefixes


def test_customer_user_service_bound_to_svp_gateway():
    docs = _load_all(_ISTIO_DIR / "virtual-services.yaml")
    vs = _vs_for(docs, "customer-user-service-vs")
    assert "svp-gateway" in vs["spec"]["gateways"]


def test_customer_user_service_has_api_customers_prefix():
    docs = _load_all(_ISTIO_DIR / "virtual-services.yaml")
    vs = _vs_for(docs, "customer-user-service-vs")
    assert "/api/customers" in _all_uri_prefixes(vs)


def test_customer_user_service_has_api_users_prefix():
    docs = _load_all(_ISTIO_DIR / "virtual-services.yaml")
    vs = _vs_for(docs, "customer-user-service-vs")
    assert "/api/users" in _all_uri_prefixes(vs)


def test_planning_service_bound_to_svp_gateway():
    docs = _load_all(_ISTIO_DIR / "virtual-services.yaml")
    vs = _vs_for(docs, "planning-service-vs")
    assert "svp-gateway" in vs["spec"]["gateways"]


def test_planning_service_has_api_plans_prefix():
    docs = _load_all(_ISTIO_DIR / "virtual-services.yaml")
    vs = _vs_for(docs, "planning-service-vs")
    assert "/api/plans" in _all_uri_prefixes(vs)


def test_expense_service_bound_to_svp_gateway():
    docs = _load_all(_ISTIO_DIR / "virtual-services.yaml")
    vs = _vs_for(docs, "expense-service-vs")
    assert "svp-gateway" in vs["spec"]["gateways"]


def test_expense_service_has_api_expenses_prefix():
    docs = _load_all(_ISTIO_DIR / "virtual-services.yaml")
    vs = _vs_for(docs, "expense-service-vs")
    assert "/api/expenses" in _all_uri_prefixes(vs)


def test_frontend_service_bound_to_svp_gateway():
    docs = _load_all(_ISTIO_DIR / "virtual-services.yaml")
    vs = _vs_for(docs, "frontend-service-vs")
    assert "svp-gateway" in vs["spec"]["gateways"]


def test_frontend_service_catch_all_prefix_is_last():
    docs = _load_all(_ISTIO_DIR / "virtual-services.yaml")
    vs = _vs_for(docs, "frontend-service-vs")
    http_rules = vs["spec"]["http"]
    last_prefixes = _all_uri_prefixes({"spec": {"http": [http_rules[-1]]}})
    assert "/" in last_prefixes


def test_all_four_virtual_services_present():
    docs = _load_all(_ISTIO_DIR / "virtual-services.yaml")
    assert len(docs) == 4
