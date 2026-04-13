"""Plan projection handler for the Planning Service.

Exposes one public coroutine:
- update_plan_projection -- upsert the plan read-model.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from planning_service.models import (
    Call,
    DayPlan,
    PlanReadModel,
    Visit,
)
from shared.logger import logger


async def update_plan_projection(
    plan_id: UUID, db: AsyncSession
) -> None:
    """Upsert the read-model row for the given plan.

    Reads the current state of the plan from the write-side
    tables, counts its visits and calls, then inserts or
    updates the corresponding ``plan_read_model`` row.

    Does nothing and logs a warning if the plan is not found.

    Arguments:
    plan_id -- UUID of the plan to project.
    db      -- active database session.
    """
    plan_result = await db.execute(
        select(DayPlan).where(DayPlan.id == plan_id)
    )
    plan = plan_result.scalar_one_or_none()
    if plan is None:
        logger.warning(
            "update_plan_projection: plan %s not found.",
            plan_id,
        )
        return

    visit_count_result = await db.execute(
        select(func.count()).select_from(Visit).where(
            Visit.plan_id == plan_id
        )
    )
    visit_count: int = visit_count_result.scalar_one()

    call_count_result = await db.execute(
        select(func.count()).select_from(Call).where(
            Call.plan_id == plan_id
        )
    )
    call_count: int = call_count_result.scalar_one()

    read_result = await db.execute(
        select(PlanReadModel).where(
            PlanReadModel.id == plan_id
        )
    )
    read_model = read_result.scalar_one_or_none()

    now = datetime.utcnow()

    if read_model is None:
        read_model = PlanReadModel(
            id=plan_id,
            rep_id=plan.rep_id,
            status=plan.status.value,
            date=plan.date,
            visit_count=visit_count,
            call_count=call_count,
            created_at=now,
            updated_at=now,
        )
        db.add(read_model)
        logger.debug(
            "Projection inserted for plan %s.", plan_id
        )
    else:
        read_model.rep_id = plan.rep_id
        read_model.status = plan.status.value
        read_model.date = plan.date
        read_model.visit_count = visit_count
        read_model.call_count = call_count
        read_model.updated_at = now
        logger.debug(
            "Projection updated for plan %s.", plan_id
        )

    await db.commit()
    logger.info(
        "Plan projection upserted for plan %s "
        "(%d visits, %d calls).",
        plan_id,
        visit_count,
        call_count,
    )
