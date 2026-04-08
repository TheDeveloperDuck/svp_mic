"""Read-side expenses router for the Expense Service.

Endpoints:
- GET /expenses/read/rep/{rep_id}   -- expense summaries for a rep.
- GET /expenses/read/status/{status} -- expenses filtered by status.
- GET /expenses/read/history         -- full history with filters.
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from expense_service.database import get_db
from expense_service.models import ExpenseReadModel
from expense_service.schemas import ExpenseReadModelResponse
from shared.logger import logger


router = APIRouter(prefix="/expenses/read", tags=["expenses-read"])


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/rep/{rep_id}",
    response_model=list[ExpenseReadModelResponse],
)
async def get_expenses_for_rep(
    rep_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[ExpenseReadModelResponse]:
    """Return all expense summaries for the given sales rep.

    Arguments:
    rep_id -- UUID of the sales rep.

    Return value:
    list[ExpenseReadModelResponse] -- matching expense summaries.
    """
    result = await db.execute(
        select(ExpenseReadModel).where(
            ExpenseReadModel.rep_id == rep_id
        )
    )
    rows = list(result.scalars().all())
    logger.debug(
        "GET /expenses/read/rep/%s → %d records.",
        rep_id,
        len(rows),
    )
    return [
        ExpenseReadModelResponse.model_validate(r) for r in rows
    ]


@router.get(
    "/status/{status}",
    response_model=list[ExpenseReadModelResponse],
)
async def get_expenses_by_status(
    status: str,
    db: AsyncSession = Depends(get_db),
) -> list[ExpenseReadModelResponse]:
    """Return all expenses with the given status string.

    Arguments:
    status -- status string to filter by.

    Return value:
    list[ExpenseReadModelResponse] -- matching expense summaries.
    """
    result = await db.execute(
        select(ExpenseReadModel).where(
            ExpenseReadModel.status == status
        )
    )
    rows = list(result.scalars().all())
    logger.debug(
        "GET /expenses/read/status/%s → %d records.",
        status,
        len(rows),
    )
    return [
        ExpenseReadModelResponse.model_validate(r) for r in rows
    ]


@router.get(
    "/history",
    response_model=list[ExpenseReadModelResponse],
)
async def get_expense_history(
    rep_id: UUID | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[ExpenseReadModelResponse]:
    """Return the full expense history with optional filters.

    Query parameters:
    rep_id -- optional UUID to filter by sales rep.
    status -- optional status string to filter results.

    Return value:
    list[ExpenseReadModelResponse] -- matching expense summaries.
    """
    query = select(ExpenseReadModel)
    if rep_id is not None:
        query = query.where(ExpenseReadModel.rep_id == rep_id)
    if status is not None:
        query = query.where(ExpenseReadModel.status == status)
    result = await db.execute(query)
    rows = list(result.scalars().all())
    logger.debug(
        "GET /expenses/read/history → %d records "
        "(rep_id=%s, status=%s).",
        len(rows),
        rep_id,
        status,
    )
    return [
        ExpenseReadModelResponse.model_validate(r) for r in rows
    ]
