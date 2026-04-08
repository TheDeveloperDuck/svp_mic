"""Pydantic request and response schemas for the Expense Service.

Each database model has a paired ``Create`` schema (used for inbound
request validation) and a ``Response`` schema (used to serialise outbound
data).  Response schemas are configured with ``from_attributes=True`` so
they can be built directly from SQLAlchemy ORM instances.

Exported schemas:
- ExpenseSubmissionCreate, ExpenseSubmissionResponse
- ExpenseReadModelResponse
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from expense_service.models import ExpenseCategory, ExpenseStatus
from shared.logger import logger


# ---------------------------------------------------------------------------
# ExpenseSubmission
# ---------------------------------------------------------------------------

class ExpenseSubmissionCreate(BaseModel):
    """Schema for creating a new expense submission.

    Fields:
    rep_id        -- UUID of the submitting sales rep.
    plan_id       -- UUID of the associated day plan.
    category      -- one of ``fuel``, ``food``, ``overnight_stay``, ``tolls``.
    amount        -- claimed amount.
    description   -- optional free-text description.
    receipt_image -- optional base64-encoded receipt image.
    """

    rep_id: UUID
    plan_id: UUID
    category: ExpenseCategory
    amount: Decimal
    description: str | None = None
    receipt_image: str | None = None


class ExpenseSubmissionResponse(BaseModel):
    """Schema for serialising an expense submission in API responses.

    Fields:
    id            -- UUID primary key.
    rep_id        -- UUID of the submitting sales rep.
    plan_id       -- UUID of the associated day plan.
    category      -- expense category.
    amount        -- claimed amount.
    description   -- optional free-text description.
    receipt_image -- optional base64-encoded receipt image.
    status        -- current approval status.
    submitted_at  -- UTC creation timestamp.
    decided_at    -- UTC decision timestamp; ``None`` if not yet decided.
    decided_by    -- UUID of the deciding manager; ``None`` if not yet decided.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rep_id: UUID
    plan_id: UUID
    category: ExpenseCategory
    amount: Decimal
    description: str | None
    receipt_image: str | None
    status: ExpenseStatus
    submitted_at: datetime
    decided_at: datetime | None
    decided_by: UUID | None


logger.debug("ExpenseSubmission schemas loaded.")


# ---------------------------------------------------------------------------
# ExpenseReadModel
# ---------------------------------------------------------------------------

class ExpenseReadModelResponse(BaseModel):
    """Schema for serialising an expense read-model row.

    Fields:
    id           -- UUID primary key.
    rep_id       -- UUID of the sales rep.
    plan_id      -- UUID of the associated day plan.
    category     -- expense category string.
    amount       -- claimed amount.
    status       -- current status string.
    submitted_at -- UTC timestamp when the expense was submitted.
    decided_at   -- UTC decision timestamp; ``None`` if not yet decided.
    updated_at   -- UTC timestamp of the last projection update.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rep_id: UUID
    plan_id: UUID
    category: str
    amount: Decimal
    status: str
    submitted_at: datetime
    decided_at: datetime | None
    updated_at: datetime


logger.debug("ExpenseReadModel schemas loaded.")
