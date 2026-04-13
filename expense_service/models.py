"""SQLAlchemy ORM models for the Expense Service.

Defines two database tables:

- ``ExpenseSubmission`` -- a sales rep's expense claim.
- ``ExpenseReadModel`` -- denormalised read-side projection of an expense.
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from shared.logger import logger


class Base(DeclarativeBase):
    """Shared declarative base for all Expense Service ORM models."""

    pass


class ExpenseCategory(str, enum.Enum):
    """Enumeration of valid expense categories."""

    fuel = "fuel"
    food = "food"
    overnight_stay = "overnight_stay"
    tolls = "tolls"


class ExpenseStatus(str, enum.Enum):
    """Enumeration of valid statuses for an expense submission."""

    submitted = "submitted"
    pending_approval = "pending_approval"
    approved = "approved"
    rejected = "rejected"


class ExpenseSubmission(Base):
    """ORM model for the ``expense_submission`` table.

    Represents a sales rep's expense claim, including the category,
    amount, optional receipt image, and approval status.

    Public attributes:
    id            -- UUID primary key.
    rep_id        -- UUID of the submitting sales rep (no cross-service FK).
    plan_id       -- UUID of the associated day plan (no cross-service FK).
    category      -- one of ``fuel``, ``food``, ``overnight_stay``, ``tolls``.
    amount        -- claimed amount, stored with precision 10 and scale 2.
    description   -- optional free-text description.
    receipt_image -- optional base64-encoded receipt image.
    status        -- one of ``submitted``, ``pending_approval``, ``approved``,
                     ``rejected``.
    submitted_at  -- UTC timestamp set at insert time.
    decided_at    -- UTC timestamp when the claim was approved or rejected.
    decided_by    -- UUID of the deciding manager (no cross-service FK).
    """

    __tablename__ = "expense_submission"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    rep_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    category: Mapped[ExpenseCategory] = mapped_column(
        SAEnum(ExpenseCategory, name="expensecategory"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=2),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    receipt_image: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ExpenseStatus] = mapped_column(
        SAEnum(ExpenseStatus, name="expensestatus"),
        nullable=False,
        default=ExpenseStatus.submitted,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        """Return an unambiguous string representation of the ExpenseSubmission instance."""
        return (
            f"<ExpenseSubmission id={self.id}"
            f" rep_id={self.rep_id}"
            f" status={self.status}>"
        )


logger.debug("ExpenseSubmission model registered.")


class ExpenseReadModel(Base):
    """ORM model for the ``expense_read_model`` table.

    Denormalised read-side projection of an expense submission, maintained
    by event handlers.  Used to serve list and summary queries without
    joining the write-side tables.

    Public attributes:
    id           -- UUID primary key.
    rep_id       -- UUID of the sales rep.
    plan_id      -- UUID of the associated day plan.
    category     -- expense category string.
    amount       -- claimed amount, stored with precision 10 and scale 2.
    status       -- current status string.
    submitted_at -- UTC timestamp when the expense was submitted.
    decided_at   -- UTC timestamp when the expense was decided; nullable.
    updated_at   -- UTC timestamp of the most recent projection update.
    """

    __tablename__ = "expense_read_model"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    rep_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=2),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    def __repr__(self) -> str:
        """Return an unambiguous string representation of the ExpenseReadModel instance."""
        return (
            f"<ExpenseReadModel id={self.id}"
            f" rep_id={self.rep_id}"
            f" status={self.status}>"
        )


logger.debug("ExpenseReadModel model registered.")
