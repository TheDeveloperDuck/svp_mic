"""Page rendering router for the Frontend Service.

All routes return rendered Jinja2 HTML responses.  Each route fetches
data from the relevant backend services via the nginx reverse proxy at
``http://nginx/api/...``.  On any HTTP or network error the route logs
the failure and falls back to empty collections so the page still
renders.

Endpoints:
- GET /                  -- home / index page.
- GET /rep/plan          -- rep day-plan builder.
- GET /rep/execute       -- rep plan execution view.
- GET /rep/expenses      -- rep expense submission and history.
- GET /manager/expenses  -- manager expense approval queue.
- GET /manager/overview  -- manager team overview.
- GET /admin/users       -- admin user management.
- GET /admin/customers   -- admin customer management.
"""

from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from shared.logger import logger
from shared.tracing import build_tracing_headers


# Populated by main.py after the Jinja2Templates instance is created.
templates: Jinja2Templates | None = None

router = APIRouter(tags=["pages"])

_NGINX_BASE = "http://nginx/api"
_TIMEOUT = 10.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _get(url: str, headers: dict | None = None) -> Any:
    """Perform a GET request and return the parsed JSON body.

    On any ``httpx`` error the exception is logged and an empty list is
    returned so callers can degrade gracefully.

    Arguments:
    url     -- fully-qualified URL to request.
    headers -- optional headers to forward (e.g. B3 tracing headers).

    Return value:
    Any -- parsed JSON value, or an empty list on error.
    """
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(url, headers=headers or {})
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        logger.error("HTTP error fetching %s: %s", url, exc)
        return []


def _ctx(request: Request, extra: dict[str, Any]) -> dict[str, Any]:
    """Build a base template context enriched with page-specific data.

    Every template receives ``request`` and ``current_path`` so that
    the base layout can highlight the active navigation link.

    Arguments:
    request -- the incoming FastAPI request.
    extra   -- page-specific variables to merge into the context.

    Return value:
    dict[str, Any] -- merged template context.
    """
    return {"request": request, "current_path": request.url.path, **extra}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Render the home page.

    Return value:
    HTMLResponse -- rendered ``index.html`` template.
    """
    return templates.TemplateResponse(
        request,
        "index.html",
        _ctx(request, {}),
    )


@router.get("/rep/plan", response_class=HTMLResponse)
async def rep_plan(request: Request) -> HTMLResponse:
    """Render the rep day-plan builder page.

    Fetches the full customer list from the customer service so the rep
    can pick customers to add to their plan.

    Return value:
    HTMLResponse -- rendered ``rep/plan.html`` template.
    """
    customers = await _get(f"{_NGINX_BASE}/customers", build_tracing_headers(request))
    if not isinstance(customers, list):
        logger.error(
            "Unexpected response type for /customers: %s",
            type(customers),
        )
        customers = []
    return templates.TemplateResponse(
        request,
        "rep/plan.html",
        _ctx(request, {"customers": customers}),
    )


@router.get("/rep/execute", response_class=HTMLResponse)
async def rep_execute(request: Request) -> HTMLResponse:
    """Render the rep plan execution page.

    Fetches the list of plans so the rep can select one to work through.

    Return value:
    HTMLResponse -- rendered ``rep/execute.html`` template.
    """
    plans = await _get(f"{_NGINX_BASE}/plans", build_tracing_headers(request))
    if not isinstance(plans, list):
        logger.error(
            "Unexpected response type for /plans: %s",
            type(plans),
        )
        plans = []
    return templates.TemplateResponse(
        request,
        "rep/execute.html",
        _ctx(request, {"plans": plans}),
    )


@router.get("/rep/expenses", response_class=HTMLResponse)
async def rep_expenses(
    request: Request,
    rep_id: str = "",
) -> HTMLResponse:
    """Render the rep expense submission and history page.

    When ``rep_id`` is provided the expense list is filtered server-side
    by passing it as a query parameter to the expense service.

    Query parameters:
    rep_id -- optional rep identifier; defaults to empty string.

    Return value:
    HTMLResponse -- rendered ``rep/expenses.html`` template.
    """
    if rep_id:
        url = f"{_NGINX_BASE}/expenses?rep_id={rep_id}"
    else:
        url = f"{_NGINX_BASE}/expenses"

    expenses = await _get(url, build_tracing_headers(request))
    if not isinstance(expenses, list):
        logger.error(
            "Unexpected response type for /expenses: %s",
            type(expenses),
        )
        expenses = []
    return templates.TemplateResponse(
        request,
        "rep/expenses.html",
        _ctx(request, {"expenses": expenses, "rep_id": rep_id}),
    )


@router.get("/manager/expenses", response_class=HTMLResponse)
async def manager_approvals(request: Request) -> HTMLResponse:
    """Render the manager expense approval queue page.

    Fetches all expense submissions regardless of status so the manager
    can filter and act on them.

    Return value:
    HTMLResponse -- rendered ``manager/approvals.html`` template.
    """
    expenses = await _get(f"{_NGINX_BASE}/expenses", build_tracing_headers(request))
    if not isinstance(expenses, list):
        logger.error(
            "Unexpected response type for /expenses: %s",
            type(expenses),
        )
        expenses = []
    return templates.TemplateResponse(
        request,
        "manager/approvals.html",
        _ctx(request, {"expenses": expenses}),
    )


@router.get("/manager/overview", response_class=HTMLResponse)
async def manager_overview(request: Request) -> HTMLResponse:
    """Render the manager team overview page.

    Fetches plan history and expense history in parallel from the
    respective read-side endpoints.

    Return value:
    HTMLResponse -- rendered ``manager/overview.html`` template.
    """
    plans = await _get(f"{_NGINX_BASE}/plans/read/history", build_tracing_headers(request))
    if not isinstance(plans, list):
        logger.error(
            "Unexpected response type for /plans/read/history: %s",
            type(plans),
        )
        plans = []

    expenses = await _get(f"{_NGINX_BASE}/expenses/read/history", build_tracing_headers(request))
    if not isinstance(expenses, list):
        logger.error(
            "Unexpected response type for /expenses/read/history: %s",
            type(expenses),
        )
        expenses = []

    return templates.TemplateResponse(
        request,
        "manager/overview.html",
        _ctx(request, {"plans": plans, "expenses": expenses}),
    )


@router.get("/admin/users", response_class=HTMLResponse)
async def admin_users(request: Request) -> HTMLResponse:
    """Render the admin user management page.

    Fetches the full user list from the user service.

    Return value:
    HTMLResponse -- rendered ``admin/users.html`` template.
    """
    users = await _get(f"{_NGINX_BASE}/users", build_tracing_headers(request))
    if not isinstance(users, list):
        logger.error(
            "Unexpected response type for /users: %s",
            type(users),
        )
        users = []
    return templates.TemplateResponse(
        request,
        "admin/users.html",
        _ctx(request, {"users": users}),
    )


@router.get("/admin/customers", response_class=HTMLResponse)
async def admin_customers(request: Request) -> HTMLResponse:
    """Render the admin customer management page.

    Fetches the full customer list from the customer service.

    Return value:
    HTMLResponse -- rendered ``admin/customers.html`` template.
    """
    customers = await _get(f"{_NGINX_BASE}/customers", build_tracing_headers(request))
    if not isinstance(customers, list):
        logger.error(
            "Unexpected response type for /customers: %s",
            type(customers),
        )
        customers = []
    return templates.TemplateResponse(
        request,
        "admin/customers.html",
        _ctx(request, {"customers": customers}),
    )
