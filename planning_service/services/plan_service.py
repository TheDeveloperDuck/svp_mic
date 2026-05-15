"""Business logic and state transition rules for the Planning Service.

Enforces the following rules:

- A plan cannot be confirmed without at least one visit or call.
- A visit cannot be marked complete without ``outcome_notes``.
- Plan state transitions follow the sequence:
  ``draft`` → ``confirmed`` → ``active`` → ``completed``.

Exposed async functions:
- create_plan
- get_plan
- list_plans
- confirm_plan
- activate_plan
- complete_plan
- add_visit
- add_call
- update_visit
- update_call
"""

from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planning_service.models import (
    Call,
    CallStatus,
    DayPlan,
    DayPlanStatus,
    Outbox,
    Visit,
    VisitStatus,
)
from planning_service.projections.plan_projection import update_plan_projection
from planning_service.schemas import CallCreate, DayPlanCreate, VisitCreate
from shared.exceptions import PlanConfirmationError, VisitCompletionError
from shared.logger import logger


async def create_plan(payload: DayPlanCreate, db: AsyncSession) -> DayPlan:
    """Create a new day plan in ``draft`` state.

    Raises ``ValueError`` if the ``rep_id`` does not correspond to a known
    user in the Customer User Service.

    Arguments:
    payload -- validated creation data.
    db      -- active database session.

    Return value:
    DayPlan -- the newly persisted plan ORM instance.
    """
    async with httpx.AsyncClient(timeout=30.0) as http:
        rep_resp = await http.get(
            f"http://customer-user-service:8001/users/{payload.rep_id}"
        )
    if rep_resp.status_code == 404:
        raise ValueError(f"Rep {payload.rep_id} not found.")

    plan = DayPlan(**payload.model_dump())
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    await update_plan_projection(plan.id, db)
    logger.info("Plan created: %s.", plan.id)
    return plan


async def get_plan(plan_id: UUID, db: AsyncSession) -> DayPlan | None:
    """Return the plan with the given ID, or ``None`` if not found.

    Arguments:
    plan_id -- UUID of the plan to fetch.
    db      -- active database session.

    Return value:
    DayPlan | None -- the matching ORM instance, or ``None``.
    """
    result = await db.execute(select(DayPlan).where(DayPlan.id == plan_id))
    return result.scalar_one_or_none()


async def list_plans(
    db: AsyncSession,
    rep_id: UUID | None = None,
) -> list[DayPlan]:
    """Return all day plans, optionally filtered by sales rep.

    Arguments:
    db     -- active database session.
    rep_id -- optional UUID to restrict results to a single rep.

    Return value:
    list[DayPlan] -- matching plan ORM instances.
    """
    query = select(DayPlan)
    if rep_id is not None:
        query = query.where(DayPlan.rep_id == rep_id)
    result = await db.execute(query)
    return list(result.scalars().all())


async def confirm_plan(plan_id: UUID, db: AsyncSession) -> DayPlan:
    """Transition a plan from ``draft`` to ``confirmed``.

    Raises ``PlanConfirmationError`` when the plan has no visits or calls.
    Raises ``ValueError`` when the plan is not in ``draft`` state or does
    not exist.

    Arguments:
    plan_id -- UUID of the plan to confirm.
    db      -- active database session.

    Return value:
    DayPlan -- the updated plan ORM instance.
    """
    plan = await get_plan(plan_id, db)
    if plan is None:
        raise ValueError(f"Plan {plan_id} not found.")
    if plan.status != DayPlanStatus.draft:
        raise ValueError(
            f"Plan {plan_id} cannot be confirmed from status '{plan.status}'."
        )

    visits_result = await db.execute(
        select(Visit).where(Visit.plan_id == plan_id)
    )
    calls_result = await db.execute(
        select(Call).where(Call.plan_id == plan_id)
    )
    if not visits_result.scalars().all() and not calls_result.scalars().all():
        raise PlanConfirmationError(
            f"Plan {plan_id} must have at least one visit or call before it"
            " can be confirmed."
        )

    plan.status = DayPlanStatus.confirmed
    outbox_row = Outbox(
        event_type="plan.confirmed",
        aggregate_id=plan.id,
        payload={"plan_id": str(plan.id), "rep_id": str(plan.rep_id)},
    )
    db.add(outbox_row)
    await db.commit()
    await db.refresh(plan)
    await update_plan_projection(plan.id, db)
    logger.info("Plan confirmed: %s.", plan_id)
    return plan


async def activate_plan(plan_id: UUID, db: AsyncSession) -> DayPlan:
    """Transition a plan from ``confirmed`` to ``active``.

    Raises ``ValueError`` when the plan is not in ``confirmed`` state or
    does not exist.

    Arguments:
    plan_id -- UUID of the plan to activate.
    db      -- active database session.

    Return value:
    DayPlan -- the updated plan ORM instance.
    """
    plan = await get_plan(plan_id, db)
    if plan is None:
        raise ValueError(f"Plan {plan_id} not found.")
    if plan.status != DayPlanStatus.confirmed:
        raise ValueError(
            f"Plan {plan_id} cannot be activated from status '{plan.status}'."
        )

    plan.status = DayPlanStatus.active
    await db.commit()
    await db.refresh(plan)
    await update_plan_projection(plan.id, db)
    logger.info("Plan activated: %s.", plan_id)
    return plan


async def complete_plan(plan_id: UUID, db: AsyncSession) -> DayPlan:
    """Transition a plan from ``active`` to ``completed``.

    Raises ``ValueError`` when the plan is not in ``active`` state or does
    not exist.

    Arguments:
    plan_id -- UUID of the plan to complete.
    db      -- active database session.

    Return value:
    DayPlan -- the updated plan ORM instance.
    """
    plan = await get_plan(plan_id, db)
    if plan is None:
        raise ValueError(f"Plan {plan_id} not found.")
    if plan.status != DayPlanStatus.active:
        raise ValueError(
            f"Plan {plan_id} cannot be completed from status '{plan.status}'."
        )

    plan.status = DayPlanStatus.completed
    await db.commit()
    await db.refresh(plan)
    await update_plan_projection(plan.id, db)
    logger.info("Plan completed: %s.", plan_id)
    return plan


async def add_visit(plan_id: UUID, payload: VisitCreate, db: AsyncSession) -> Visit:
    """Add a new visit to an existing plan.

    Raises ``ValueError`` if the plan does not exist.

    Arguments:
    plan_id -- UUID of the parent plan.
    payload -- validated visit creation data.
    db      -- active database session.

    Return value:
    Visit -- the newly persisted visit ORM instance.
    """
    plan = await get_plan(plan_id, db)
    if plan is None:
        raise ValueError(f"Plan {plan_id} not found.")

    data = payload.model_dump()
    data["plan_id"] = plan_id
    visit = Visit(**data)
    db.add(visit)
    await db.commit()
    await db.refresh(visit)
    await update_plan_projection(plan_id, db)
    logger.debug("Visit added to plan %s: %s.", plan_id, visit.id)
    return visit


async def add_call(plan_id: UUID, payload: CallCreate, db: AsyncSession) -> Call:
    """Add a new call to an existing plan.

    Raises ``ValueError`` if the plan does not exist.

    Arguments:
    plan_id -- UUID of the parent plan.
    payload -- validated call creation data.
    db      -- active database session.

    Return value:
    Call -- the newly persisted call ORM instance.
    """
    plan = await get_plan(plan_id, db)
    if plan is None:
        raise ValueError(f"Plan {plan_id} not found.")

    data = payload.model_dump()
    data["plan_id"] = plan_id
    call = Call(**data)
    db.add(call)
    await db.commit()
    await db.refresh(call)
    await update_plan_projection(plan_id, db)
    logger.debug("Call added to plan %s: %s.", plan_id, call.id)
    return call


async def update_visit(
    plan_id: UUID,
    visit_id: UUID,
    status: VisitStatus | None,
    outcome_notes: str | None,
    db: AsyncSession,
) -> Visit:
    """Update the status and outcome notes of a visit.

    Raises ``VisitCompletionError`` when marking a visit completed without
    providing ``outcome_notes``.  Raises ``ValueError`` when the visit does
    not exist within the given plan.

    Arguments:
    plan_id       -- UUID of the parent plan.
    visit_id      -- UUID of the visit to update.
    status        -- new status value, or ``None`` to leave unchanged.
    outcome_notes -- free-text notes, or ``None`` to leave unchanged.
    db            -- active database session.

    Return value:
    Visit -- the updated visit ORM instance.
    """
    result = await db.execute(
        select(Visit).where(Visit.id == visit_id, Visit.plan_id == plan_id)
    )
    visit = result.scalar_one_or_none()
    if visit is None:
        raise ValueError(f"Visit {visit_id} not found in plan {plan_id}.")

    if status == VisitStatus.completed and not outcome_notes:
        raise VisitCompletionError(
            f"Visit {visit_id} cannot be marked complete without outcome notes."
        )

    if status is not None:
        visit.status = status
    if outcome_notes is not None:
        visit.outcome_notes = outcome_notes

    await db.commit()
    await db.refresh(visit)
    await update_plan_projection(plan_id, db)
    logger.info("Visit updated: %s (status=%s).", visit_id, visit.status)
    return visit


async def update_call(
    plan_id: UUID,
    call_id: UUID,
    status: CallStatus | None,
    outcome_notes: str | None,
    db: AsyncSession,
) -> Call:
    """Update the status and outcome notes of a call.

    Raises ``ValueError`` when the call does not exist within the given plan.

    Arguments:
    plan_id       -- UUID of the parent plan.
    call_id       -- UUID of the call to update.
    status        -- new status value, or ``None`` to leave unchanged.
    outcome_notes -- free-text notes, or ``None`` to leave unchanged.
    db            -- active database session.

    Return value:
    Call -- the updated call ORM instance.
    """
    result = await db.execute(
        select(Call).where(Call.id == call_id, Call.plan_id == plan_id)
    )
    call = result.scalar_one_or_none()
    if call is None:
        raise ValueError(f"Call {call_id} not found in plan {plan_id}.")

    if status is not None:
        call.status = status
    if outcome_notes is not None:
        call.outcome_notes = outcome_notes

    await db.commit()
    await db.refresh(call)
    await update_plan_projection(plan_id, db)
    logger.info("Call updated: %s (status=%s).", call_id, call.status)
    return call
