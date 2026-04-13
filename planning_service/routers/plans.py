"""Plans router for the Planning Service.

Endpoints:
- POST   /plans                                    -- create a new plan.
- GET    /plans                                    -- list plans, filter by rep_id.
- GET    /plans/{plan_id}                          -- fetch a single plan.
- PATCH  /plans/{plan_id}/confirm                  -- confirm a draft plan.
- PATCH  /plans/{plan_id}/activate                 -- activate a confirmed plan.
- PATCH  /plans/{plan_id}/complete                 -- complete an active plan.
- POST   /plans/{plan_id}/visits                   -- add a visit to a plan.
- POST   /plans/{plan_id}/calls                    -- add a call to a plan.
- PATCH  /plans/{plan_id}/visits/{visit_id}        -- update visit status / notes.
- PATCH  /plans/{plan_id}/calls/{call_id}          -- update call status / notes.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from planning_service.database import get_db
from planning_service.models import CallStatus, DayPlan, VisitStatus
from planning_service.schemas import (
    CallCreate,
    CallResponse,
    DayPlanCreate,
    DayPlanResponse,
    VisitCreate,
    VisitResponse,
)
from planning_service.services import plan_service
from shared.exceptions import PlanConfirmationError, VisitCompletionError
from shared.logger import logger


# ---------------------------------------------------------------------------
# Local schemas (partial update shapes — not in schemas.py)
# ---------------------------------------------------------------------------

class VisitUpdate(BaseModel):
    """Schema for partially updating a visit record.

    All fields are optional; only supplied fields are applied.

    Fields:
    status        -- new visit status.
    outcome_notes -- free-text notes recorded after the visit.
    """

    status: VisitStatus | None = None
    outcome_notes: str | None = None


class CallUpdate(BaseModel):
    """Schema for partially updating a call record.

    All fields are optional; only supplied fields are applied.

    Fields:
    status        -- new call status.
    outcome_notes -- free-text notes recorded after the call.
    """

    status: CallStatus | None = None
    outcome_notes: str | None = None


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/plans", tags=["plans"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_plan_or_404(plan_id: UUID, db: AsyncSession) -> DayPlan:
    """Return the plan with the given ID or raise HTTP 404.

    Arguments:
    plan_id -- UUID of the plan to fetch.
    db      -- active database session.

    Return value:
    DayPlan -- the matching ORM instance.
    """
    plan = await plan_service.get_plan(plan_id, db)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan {plan_id} not found.",
        )
    return plan


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", response_model=DayPlanResponse, status_code=status.HTTP_201_CREATED)
async def create_plan(
    payload: DayPlanCreate,
    db: AsyncSession = Depends(get_db),
) -> DayPlanResponse:
    """Create a new day plan in ``draft`` state.

    Arguments:
    payload -- validated plan creation data.

    Return value:
    DayPlanResponse -- the newly created plan.
    """
    try:
        plan = await plan_service.create_plan(payload, db)
    except ValueError as exc:
        logger.warning("Plan creation rejected: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    logger.debug("POST /plans → created plan %s.", plan.id)
    return DayPlanResponse.model_validate(plan)


@router.get("", response_model=list[DayPlanResponse])
async def list_plans(
    rep_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[DayPlanResponse]:
    """Return all day plans, optionally filtered by sales rep UUID.

    Query parameters:
    rep_id -- optional UUID to restrict results to a single rep.

    Return value:
    list[DayPlanResponse] -- matching plan records.
    """
    plans = await plan_service.list_plans(db, rep_id=rep_id)
    logger.debug("GET /plans → %d records (rep_id=%s).", len(plans), rep_id)
    return [DayPlanResponse.model_validate(p) for p in plans]


@router.get("/{plan_id}", response_model=DayPlanResponse)
async def get_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> DayPlanResponse:
    """Return a single day plan by ID.

    Arguments:
    plan_id -- UUID of the plan to fetch.

    Return value:
    DayPlanResponse -- the matching plan record.
    """
    plan = await _get_plan_or_404(plan_id, db)
    return DayPlanResponse.model_validate(plan)


@router.patch("/{plan_id}/confirm", response_model=DayPlanResponse)
async def confirm_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> DayPlanResponse:
    """Transition a plan from ``draft`` to ``confirmed``.

    Requires at least one visit or call on the plan.

    Arguments:
    plan_id -- UUID of the plan to confirm.

    Return value:
    DayPlanResponse -- the updated plan record.
    """
    try:
        plan = await plan_service.confirm_plan(plan_id, db)
    except PlanConfirmationError as exc:
        logger.warning("Plan confirmation rejected: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except ValueError as exc:
        logger.warning("Plan confirm error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    return DayPlanResponse.model_validate(plan)


@router.patch("/{plan_id}/activate", response_model=DayPlanResponse)
async def activate_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> DayPlanResponse:
    """Transition a plan from ``confirmed`` to ``active``.

    Arguments:
    plan_id -- UUID of the plan to activate.

    Return value:
    DayPlanResponse -- the updated plan record.
    """
    try:
        plan = await plan_service.activate_plan(plan_id, db)
    except ValueError as exc:
        logger.warning("Plan activate error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    return DayPlanResponse.model_validate(plan)


@router.patch("/{plan_id}/complete", response_model=DayPlanResponse)
async def complete_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> DayPlanResponse:
    """Transition a plan from ``active`` to ``completed``.

    Arguments:
    plan_id -- UUID of the plan to complete.

    Return value:
    DayPlanResponse -- the updated plan record.
    """
    try:
        plan = await plan_service.complete_plan(plan_id, db)
    except ValueError as exc:
        logger.warning("Plan complete error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    return DayPlanResponse.model_validate(plan)


@router.post(
    "/{plan_id}/visits",
    response_model=VisitResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_visit(
    plan_id: UUID,
    payload: VisitCreate,
    db: AsyncSession = Depends(get_db),
) -> VisitResponse:
    """Add a new visit to an existing plan.

    The ``plan_id`` in the request body is overridden by the path parameter.

    Arguments:
    plan_id -- UUID of the parent plan.
    payload -- validated visit creation data.

    Return value:
    VisitResponse -- the newly created visit record.
    """
    try:
        visit = await plan_service.add_visit(plan_id, payload, db)
    except ValueError as exc:
        logger.warning("Add visit error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    logger.debug("POST /plans/%s/visits → created visit %s.", plan_id, visit.id)
    return VisitResponse.model_validate(visit)


@router.post(
    "/{plan_id}/calls",
    response_model=CallResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_call(
    plan_id: UUID,
    payload: CallCreate,
    db: AsyncSession = Depends(get_db),
) -> CallResponse:
    """Add a new call to an existing plan.

    The ``plan_id`` in the request body is overridden by the path parameter.

    Arguments:
    plan_id -- UUID of the parent plan.
    payload -- validated call creation data.

    Return value:
    CallResponse -- the newly created call record.
    """
    try:
        call = await plan_service.add_call(plan_id, payload, db)
    except ValueError as exc:
        logger.warning("Add call error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    logger.debug("POST /plans/%s/calls → created call %s.", plan_id, call.id)
    return CallResponse.model_validate(call)


@router.patch("/{plan_id}/visits/{visit_id}", response_model=VisitResponse)
async def update_visit(
    plan_id: UUID,
    visit_id: UUID,
    payload: VisitUpdate,
    db: AsyncSession = Depends(get_db),
) -> VisitResponse:
    """Update the status and outcome notes of a visit.

    Arguments:
    plan_id  -- UUID of the parent plan.
    visit_id -- UUID of the visit to update.
    payload  -- partial update data.

    Return value:
    VisitResponse -- the updated visit record.
    """
    try:
        visit = await plan_service.update_visit(
            plan_id,
            visit_id,
            payload.status,
            payload.outcome_notes,
            db,
        )
    except VisitCompletionError as exc:
        logger.warning("Visit completion rejected: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except ValueError as exc:
        logger.warning("Update visit error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    return VisitResponse.model_validate(visit)


@router.patch("/{plan_id}/calls/{call_id}", response_model=CallResponse)
async def update_call(
    plan_id: UUID,
    call_id: UUID,
    payload: CallUpdate,
    db: AsyncSession = Depends(get_db),
) -> CallResponse:
    """Update the status and outcome notes of a call.

    Arguments:
    plan_id -- UUID of the parent plan.
    call_id -- UUID of the call to update.
    payload -- partial update data.

    Return value:
    CallResponse -- the updated call record.
    """
    try:
        call = await plan_service.update_call(
            plan_id,
            call_id,
            payload.status,
            payload.outcome_notes,
            db,
        )
    except ValueError as exc:
        logger.warning("Update call error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    return CallResponse.model_validate(call)
