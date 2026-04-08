"""Business logic and state transition rules for the Expense Service.

Enforces the following rules:

- Only a manager can approve or reject a submission; ``manager_id`` must be
  provided on decision calls or ``ExpenseApprovalError`` is raised.
- A rejected submission may be amended and resubmitted, returning it to
  ``submitted`` state.
- Status transitions follow the sequence:
  ``submitted`` → ``pending_approval`` → ``approved`` / ``rejected`` → ``submitted``.

Exposed async functions:
- create_expense
- get_expense
- list_expenses
- submit_expense
- approve_expense
- reject_expense
- resubmit_expense
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from expense_service.models import ExpenseStatus, ExpenseSubmission
from expense_service.schemas import ExpenseSubmissionCreate
from shared.exceptions import ExpenseApprovalError
from shared.logger import logger


async def create_expense(
    payload: ExpenseSubmissionCreate,
    db: AsyncSession,
) -> ExpenseSubmission:
    """Create a new expense submission in ``submitted`` state.

    Arguments:
    payload -- validated creation data.
    db      -- active database session.

    Return value:
    ExpenseSubmission -- the newly persisted submission ORM instance.
    """
    expense = ExpenseSubmission(**payload.model_dump())
    db.add(expense)
    await db.commit()
    await db.refresh(expense)
    logger.info("Expense submission created: %s.", expense.id)
    return expense


async def get_expense(
    expense_id: UUID,
    db: AsyncSession,
) -> ExpenseSubmission | None:
    """Return the expense submission with the given ID, or ``None`` if not found.

    Arguments:
    expense_id -- UUID of the submission to fetch.
    db         -- active database session.

    Return value:
    ExpenseSubmission | None -- the matching ORM instance, or ``None``.
    """
    result = await db.execute(
        select(ExpenseSubmission).where(ExpenseSubmission.id == expense_id)
    )
    return result.scalar_one_or_none()


async def list_expenses(
    db: AsyncSession,
    rep_id: UUID | None = None,
    status: ExpenseStatus | None = None,
) -> list[ExpenseSubmission]:
    """Return all expense submissions, with optional filters.

    Arguments:
    db     -- active database session.
    rep_id -- optional UUID to restrict results to a single sales rep.
    status -- optional status to restrict results to a single status value.

    Return value:
    list[ExpenseSubmission] -- matching submission ORM instances.
    """
    query = select(ExpenseSubmission)
    if rep_id is not None:
        query = query.where(ExpenseSubmission.rep_id == rep_id)
    if status is not None:
        query = query.where(ExpenseSubmission.status == status)
    result = await db.execute(query)
    return list(result.scalars().all())


async def submit_expense(
    expense_id: UUID,
    db: AsyncSession,
) -> ExpenseSubmission:
    """Transition an expense submission from ``submitted`` to ``pending_approval``.

    Raises ``ValueError`` when the submission is not in ``submitted`` state or
    does not exist.

    Arguments:
    expense_id -- UUID of the submission to submit.
    db         -- active database session.

    Return value:
    ExpenseSubmission -- the updated submission ORM instance.
    """
    expense = await get_expense(expense_id, db)
    if expense is None:
        raise ValueError(f"Expense {expense_id} not found.")
    if expense.status != ExpenseStatus.submitted:
        raise ValueError(
            f"Expense {expense_id} cannot be submitted from status"
            f" '{expense.status}'."
        )

    expense.status = ExpenseStatus.pending_approval
    await db.commit()
    await db.refresh(expense)
    logger.info(
        "Expense %s transitioned to pending_approval.", expense_id
    )
    return expense


async def approve_expense(
    expense_id: UUID,
    manager_id: UUID,
    db: AsyncSession,
) -> ExpenseSubmission:
    """Transition an expense submission from ``pending_approval`` to ``approved``.

    Raises ``ExpenseApprovalError`` when ``manager_id`` is not provided.
    Raises ``ValueError`` when the submission is not in ``pending_approval``
    state or does not exist.

    Arguments:
    expense_id -- UUID of the submission to approve.
    manager_id -- UUID of the approving manager.
    db         -- active database session.

    Return value:
    ExpenseSubmission -- the updated submission ORM instance.
    """
    if not manager_id:
        raise ExpenseApprovalError(
            "A manager_id is required to approve an expense submission."
        )

    expense = await get_expense(expense_id, db)
    if expense is None:
        raise ValueError(f"Expense {expense_id} not found.")
    if expense.status != ExpenseStatus.pending_approval:
        raise ValueError(
            f"Expense {expense_id} cannot be approved from status"
            f" '{expense.status}'."
        )

    expense.status = ExpenseStatus.approved
    expense.decided_by = manager_id
    expense.decided_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(expense)
    logger.info(
        "Expense %s approved by manager %s.", expense_id, manager_id
    )
    return expense


async def reject_expense(
    expense_id: UUID,
    manager_id: UUID,
    db: AsyncSession,
) -> ExpenseSubmission:
    """Transition an expense submission from ``pending_approval`` to ``rejected``.

    Raises ``ExpenseApprovalError`` when ``manager_id`` is not provided.
    Raises ``ValueError`` when the submission is not in ``pending_approval``
    state or does not exist.

    Arguments:
    expense_id -- UUID of the submission to reject.
    manager_id -- UUID of the rejecting manager.
    db         -- active database session.

    Return value:
    ExpenseSubmission -- the updated submission ORM instance.
    """
    if not manager_id:
        raise ExpenseApprovalError(
            "A manager_id is required to reject an expense submission."
        )

    expense = await get_expense(expense_id, db)
    if expense is None:
        raise ValueError(f"Expense {expense_id} not found.")
    if expense.status != ExpenseStatus.pending_approval:
        raise ValueError(
            f"Expense {expense_id} cannot be rejected from status"
            f" '{expense.status}'."
        )

    expense.status = ExpenseStatus.rejected
    expense.decided_by = manager_id
    expense.decided_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(expense)
    logger.info(
        "Expense %s rejected by manager %s.", expense_id, manager_id
    )
    return expense


async def resubmit_expense(
    expense_id: UUID,
    amount: Decimal | None,
    description: str | None,
    receipt_image: str | None,
    db: AsyncSession,
) -> ExpenseSubmission:
    """Amend and resubmit a rejected expense, returning it to ``submitted`` state.

    Only ``amount``, ``description``, and ``receipt_image`` may be amended.
    Raises ``ValueError`` when the submission is not in ``rejected`` state or
    does not exist.

    Arguments:
    expense_id    -- UUID of the submission to resubmit.
    amount        -- updated claimed amount, or ``None`` to leave unchanged.
    description   -- updated description, or ``None`` to leave unchanged.
    receipt_image -- updated base64-encoded receipt image, or ``None`` to leave
                     unchanged.
    db            -- active database session.

    Return value:
    ExpenseSubmission -- the updated submission ORM instance.
    """
    expense = await get_expense(expense_id, db)
    if expense is None:
        raise ValueError(f"Expense {expense_id} not found.")
    if expense.status != ExpenseStatus.rejected:
        raise ValueError(
            f"Expense {expense_id} cannot be resubmitted from status"
            f" '{expense.status}'."
        )

    if amount is not None:
        expense.amount = amount
    if description is not None:
        expense.description = description
    if receipt_image is not None:
        expense.receipt_image = receipt_image

    expense.status = ExpenseStatus.submitted
    expense.decided_by = None
    expense.decided_at = None
    await db.commit()
    await db.refresh(expense)
    logger.info("Expense %s resubmitted.", expense_id)
    return expense
