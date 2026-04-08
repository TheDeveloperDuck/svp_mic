"""Read-side plans router for the Planning Service.

Endpoints:
- GET /plans/read/rep/{rep_id} -- plan summaries for a rep.
- GET /plans/read/active       -- all plans with active status.
- GET /plans/read/history      -- full history with filters.
"""

from datetime import date as Date
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planning_service.database import get_db
from planning_service.models import DayPlanStatus, PlanReadModel
from planning_service.schemas import PlanReadModelResponse
from shared.logger import logger


router = APIRouter(prefix="/plans/read", tags=["plans-read"])


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/rep/{rep_id}",
    response_model=list[PlanReadModelResponse],
)
async def get_plans_for_rep(
    rep_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[PlanReadModelResponse]:
    """Return all plan summaries for the given sales rep.

    Arguments:
    rep_id -- UUID of the sales rep.

    Return value:
    list[PlanReadModelResponse] -- matching plan summaries.
    """
    result = await db.execute(
        select(PlanReadModel).where(
            PlanReadModel.rep_id == rep_id
        )
    )
    rows = list(result.scalars().all())
    logger.debug(
        "GET /plans/read/rep/%s → %d records.",
        rep_id,
        len(rows),
    )
    return [
        PlanReadModelResponse.model_validate(r) for r in rows
    ]


@router.get(
    "/active",
    response_model=list[PlanReadModelResponse],
)
async def get_active_plans(
    db: AsyncSession = Depends(get_db),
) -> list[PlanReadModelResponse]:
    """Return all plans currently in ``active`` status.

    Return value:
    list[PlanReadModelResponse] -- active plan summaries.
    """
    result = await db.execute(
        select(PlanReadModel).where(
            PlanReadModel.status == DayPlanStatus.active.value
        )
    )
    rows = list(result.scalars().all())
    logger.debug(
        "GET /plans/read/active → %d records.", len(rows)
    )
    return [
        PlanReadModelResponse.model_validate(r) for r in rows
    ]


@router.get(
    "/history",
    response_model=list[PlanReadModelResponse],
)
async def get_plan_history(
    rep_id: UUID | None = None,
    date: Date | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[PlanReadModelResponse]:
    """Return the full plan history with optional filters.

    Query parameters:
    rep_id -- optional UUID to filter by sales rep.
    date   -- optional date to filter by plan date.

    Return value:
    list[PlanReadModelResponse] -- matching plan summaries.
    """
    query = select(PlanReadModel)
    if rep_id is not None:
        query = query.where(PlanReadModel.rep_id == rep_id)
    if date is not None:
        query = query.where(PlanReadModel.date == date)
    result = await db.execute(query)
    rows = list(result.scalars().all())
    logger.debug(
        "GET /plans/read/history → %d records "
        "(rep_id=%s, date=%s).",
        len(rows),
        rep_id,
        date,
    )
    return [
        PlanReadModelResponse.model_validate(r) for r in rows
    ]
