"""Expense projection handler for the Expense Service.

Exposes one public coroutine:
- update_expense_projection -- upsert the expense read-model row.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from expense_service.models import ExpenseReadModel, ExpenseSubmission
from shared.logger import logger


async def update_expense_projection(
    expense_id: UUID,
    db: AsyncSession,
) -> None:
    """Upsert the read-model row for the given expense submission.

    Reads the current state of the expense from the write-side table,
    then inserts or updates the corresponding ``expense_read_model``
    row.

    Does nothing and logs a warning if the expense is not found.

    Arguments:
    expense_id -- UUID of the expense submission to project.
    db         -- active database session.
    """
    submission_result = await db.execute(
        select(ExpenseSubmission).where(
            ExpenseSubmission.id == expense_id
        )
    )
    submission = submission_result.scalar_one_or_none()
    if submission is None:
        logger.warning(
            "update_expense_projection: expense %s not found.",
            expense_id,
        )
        return

    read_result = await db.execute(
        select(ExpenseReadModel).where(
            ExpenseReadModel.id == expense_id
        )
    )
    read_model = read_result.scalar_one_or_none()

    now = datetime.utcnow()

    if read_model is None:
        read_model = ExpenseReadModel(
            id=expense_id,
            rep_id=submission.rep_id,
            plan_id=submission.plan_id,
            category=submission.category.value,
            amount=submission.amount,
            status=submission.status.value,
            submitted_at=submission.submitted_at,
            decided_at=submission.decided_at,
            updated_at=now,
        )
        db.add(read_model)
        logger.debug(
            "Projection inserted for expense %s.", expense_id
        )
    else:
        read_model.rep_id = submission.rep_id
        read_model.plan_id = submission.plan_id
        read_model.category = submission.category.value
        read_model.amount = submission.amount
        read_model.status = submission.status.value
        read_model.submitted_at = submission.submitted_at
        read_model.decided_at = submission.decided_at
        read_model.updated_at = now
        logger.debug(
            "Projection updated for expense %s.", expense_id
        )

    await db.commit()
    logger.info(
        "Expense projection upserted for expense %s.", expense_id
    )
