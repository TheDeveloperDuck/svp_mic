"""Expenses router for the Expense Service.

Endpoints:
- POST   /expenses                          -- create a new expense submission.
- GET    /expenses                          -- list submissions; filter by rep_id or status.
- GET    /expenses/{expense_id}             -- fetch a single submission.
- PATCH  /expenses/{expense_id}/submit      -- move to pending_approval.
- PATCH  /expenses/{expense_id}/approve     -- approve a submission.
- PATCH  /expenses/{expense_id}/reject      -- reject a submission.
- PATCH  /expenses/{expense_id}/resubmit    -- amend and resubmit a rejected submission.
"""

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from expense_service.database import get_db
from expense_service.models import ExpenseStatus, ExpenseSubmission
from expense_service.schemas import ExpenseSubmissionCreate, ExpenseSubmissionResponse
from expense_service.services import expense_service
from shared.exceptions import ExpenseApprovalError
from shared.logger import logger


# ---------------------------------------------------------------------------
# Local schemas (decision and amendment shapes — not in schemas.py)
# ---------------------------------------------------------------------------

class ExpenseDecision(BaseModel):
    """Schema for approve and reject request bodies.

    Fields:
    manager_id -- UUID of the manager making the decision.
    """

    manager_id: UUID


class ExpenseAmendment(BaseModel):
    """Schema for amending a rejected expense on resubmission.

    All fields are optional; only supplied fields are applied.

    Fields:
    amount        -- updated claimed amount.
    description   -- updated free-text description.
    receipt_image -- updated base64-encoded receipt image.
    """

    amount: Decimal | None = None
    description: str | None = None
    receipt_image: str | None = None


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/expenses", tags=["expenses"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_expense_or_404(
    expense_id: UUID,
    db: AsyncSession,
) -> ExpenseSubmission:
    """Return the expense submission with the given ID or raise HTTP 404.

    Arguments:
    expense_id -- UUID of the submission to fetch.
    db         -- active database session.

    Return value:
    ExpenseSubmission -- the matching ORM instance.
    """
    expense = await expense_service.get_expense(expense_id, db)
    if expense is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Expense {expense_id} not found.",
        )
    return expense


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=ExpenseSubmissionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_expense(
    payload: ExpenseSubmissionCreate,
    db: AsyncSession = Depends(get_db),
) -> ExpenseSubmissionResponse:
    """Create a new expense submission in ``submitted`` state.

    Arguments:
    payload -- validated expense creation data.

    Return value:
    ExpenseSubmissionResponse -- the newly created submission.
    """
    expense = await expense_service.create_expense(payload, db)
    logger.debug("POST /expenses → created expense %s.", expense.id)
    return ExpenseSubmissionResponse.model_validate(expense)


@router.get("", response_model=list[ExpenseSubmissionResponse])
async def list_expenses(
    rep_id: UUID | None = None,
    expense_status: ExpenseStatus | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[ExpenseSubmissionResponse]:
    """Return all expense submissions, optionally filtered by rep or status.

    Query parameters:
    rep_id         -- optional UUID to restrict results to a single sales rep.
    expense_status -- optional status value to restrict results.

    Return value:
    list[ExpenseSubmissionResponse] -- matching submission records.
    """
    expenses = await expense_service.list_expenses(
        db, rep_id=rep_id, status=expense_status
    )
    logger.debug(
        "GET /expenses → %d records (rep_id=%s, status=%s).",
        len(expenses),
        rep_id,
        expense_status,
    )
    return [ExpenseSubmissionResponse.model_validate(e) for e in expenses]


@router.get("/{expense_id}", response_model=ExpenseSubmissionResponse)
async def get_expense(
    expense_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ExpenseSubmissionResponse:
    """Return a single expense submission by ID.

    Arguments:
    expense_id -- UUID of the submission to fetch.

    Return value:
    ExpenseSubmissionResponse -- the matching submission record.
    """
    expense = await _get_expense_or_404(expense_id, db)
    return ExpenseSubmissionResponse.model_validate(expense)


@router.patch("/{expense_id}/submit", response_model=ExpenseSubmissionResponse)
async def submit_expense(
    expense_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ExpenseSubmissionResponse:
    """Transition an expense submission from ``submitted`` to ``pending_approval``.

    Arguments:
    expense_id -- UUID of the submission to submit.

    Return value:
    ExpenseSubmissionResponse -- the updated submission record.
    """
    try:
        expense = await expense_service.submit_expense(expense_id, db)
    except ValueError as exc:
        logger.warning("Expense submit error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    return ExpenseSubmissionResponse.model_validate(expense)


@router.patch("/{expense_id}/approve", response_model=ExpenseSubmissionResponse)
async def approve_expense(
    expense_id: UUID,
    payload: ExpenseDecision,
    db: AsyncSession = Depends(get_db),
) -> ExpenseSubmissionResponse:
    """Approve an expense submission; requires ``manager_id`` in request body.

    Arguments:
    expense_id -- UUID of the submission to approve.
    payload    -- decision body containing ``manager_id``.

    Return value:
    ExpenseSubmissionResponse -- the updated submission record.
    """
    try:
        expense = await expense_service.approve_expense(
            expense_id, payload.manager_id, db
        )
    except ExpenseApprovalError as exc:
        logger.warning("Expense approval rejected: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except ValueError as exc:
        logger.warning("Expense approve error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    return ExpenseSubmissionResponse.model_validate(expense)


@router.patch("/{expense_id}/reject", response_model=ExpenseSubmissionResponse)
async def reject_expense(
    expense_id: UUID,
    payload: ExpenseDecision,
    db: AsyncSession = Depends(get_db),
) -> ExpenseSubmissionResponse:
    """Reject an expense submission; requires ``manager_id`` in request body.

    Arguments:
    expense_id -- UUID of the submission to reject.
    payload    -- decision body containing ``manager_id``.

    Return value:
    ExpenseSubmissionResponse -- the updated submission record.
    """
    try:
        expense = await expense_service.reject_expense(
            expense_id, payload.manager_id, db
        )
    except ExpenseApprovalError as exc:
        logger.warning("Expense rejection rejected: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except ValueError as exc:
        logger.warning("Expense reject error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    return ExpenseSubmissionResponse.model_validate(expense)


@router.patch("/{expense_id}/resubmit", response_model=ExpenseSubmissionResponse)
async def resubmit_expense(
    expense_id: UUID,
    payload: ExpenseAmendment,
    db: AsyncSession = Depends(get_db),
) -> ExpenseSubmissionResponse:
    """Amend and resubmit a rejected expense, returning it to ``submitted`` state.

    Arguments:
    expense_id -- UUID of the submission to resubmit.
    payload    -- optional amendment fields to apply before resubmission.

    Return value:
    ExpenseSubmissionResponse -- the updated submission record.
    """
    try:
        expense = await expense_service.resubmit_expense(
            expense_id,
            payload.amount,
            payload.description,
            payload.receipt_image,
            db,
        )
    except ValueError as exc:
        logger.warning("Expense resubmit error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    return ExpenseSubmissionResponse.model_validate(expense)
