from shared.tracing import build_tracing_headers, extract_tracing_headers

_B3_HEADERS = (
    "x-request-id",
    "x-b3-traceid",
    "x-b3-spanid",
    "x-b3-parentspanid",
    "x-b3-sampled",
    "x-b3-flags",
    "x-forwarded-for",
)


class FakeRequest:
    def __init__(self, headers: dict):
        self.headers = headers


def test_extract_returns_only_present_headers():
    req = FakeRequest({"x-b3-traceid": "abc", "x-request-id": "123"})
    result = extract_tracing_headers(req)
    assert set(result.keys()) == {"x-b3-traceid", "x-request-id"}


def test_extract_skips_absent_headers():
    req = FakeRequest({"x-b3-traceid": "abc"})
    result = extract_tracing_headers(req)
    assert "x-b3-spanid" not in result


def test_extract_empty_when_no_tracing_headers():
    req = FakeRequest({"content-type": "application/json"})
    result = extract_tracing_headers(req)
    assert result == {}


def test_extract_x_request_id_alone():
    req = FakeRequest({"x-request-id": "rid-1"})
    result = extract_tracing_headers(req)
    assert list(result.keys()) == ["x-request-id"]
    assert result["x-request-id"] == "rid-1"


def test_extract_x_b3_traceid_alone():
    req = FakeRequest({"x-b3-traceid": "trace-1"})
    result = extract_tracing_headers(req)
    assert list(result.keys()) == ["x-b3-traceid"]
    assert result["x-b3-traceid"] == "trace-1"


def test_extract_x_b3_spanid_alone():
    req = FakeRequest({"x-b3-spanid": "span-1"})
    result = extract_tracing_headers(req)
    assert list(result.keys()) == ["x-b3-spanid"]
    assert result["x-b3-spanid"] == "span-1"


def test_extract_x_b3_parentspanid_alone():
    req = FakeRequest({"x-b3-parentspanid": "parent-1"})
    result = extract_tracing_headers(req)
    assert list(result.keys()) == ["x-b3-parentspanid"]
    assert result["x-b3-parentspanid"] == "parent-1"


def test_extract_x_b3_sampled_alone():
    req = FakeRequest({"x-b3-sampled": "1"})
    result = extract_tracing_headers(req)
    assert list(result.keys()) == ["x-b3-sampled"]
    assert result["x-b3-sampled"] == "1"


def test_extract_x_b3_flags_alone():
    req = FakeRequest({"x-b3-flags": "0"})
    result = extract_tracing_headers(req)
    assert list(result.keys()) == ["x-b3-flags"]
    assert result["x-b3-flags"] == "0"


def test_extract_x_forwarded_for_alone():
    req = FakeRequest({"x-forwarded-for": "10.0.0.1"})
    result = extract_tracing_headers(req)
    assert list(result.keys()) == ["x-forwarded-for"]
    assert result["x-forwarded-for"] == "10.0.0.1"


def test_extract_all_seven_headers():
    headers = {h: f"val-{i}" for i, h in enumerate(_B3_HEADERS)}
    req = FakeRequest(headers)
    result = extract_tracing_headers(req)
    assert set(result.keys()) == set(_B3_HEADERS)


def test_build_returns_same_as_extract():
    req = FakeRequest({"x-b3-traceid": "t", "x-b3-spanid": "s", "x-request-id": "r"})
    assert build_tracing_headers(req) == extract_tracing_headers(req)


def test_build_empty_when_no_headers():
    req = FakeRequest({})
    assert build_tracing_headers(req) == {}


def test_build_returns_only_present():
    req = FakeRequest({"x-b3-traceid": "t", "x-b3-sampled": "1"})
    result = build_tracing_headers(req)
    assert len(result) == 2
    assert set(result.keys()) == {"x-b3-traceid", "x-b3-sampled"}


def test_neither_raises_with_no_headers():
    req = FakeRequest({})
    extract_tracing_headers(req)
    build_tracing_headers(req)
