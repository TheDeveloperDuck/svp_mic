from fastapi import Request

_TRACING_HEADERS = (
    "x-request-id",
    "x-b3-traceid",
    "x-b3-spanid",
    "x-b3-parentspanid",
    "x-b3-sampled",
    "x-b3-flags",
    "x-forwarded-for",
)


def extract_tracing_headers(request: Request) -> dict:
    return {h: request.headers[h] for h in _TRACING_HEADERS if h in request.headers}


def build_tracing_headers(request: Request) -> dict:
    return extract_tracing_headers(request)
