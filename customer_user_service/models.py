"""SQLAlchemy ORM models for the Customer User Service.

Defines four database tables:

- ``User`` -- service accounts with a role-based access level.
- ``Customer`` -- customer records with optional geolocation and rep assignment.
- ``ManagerRep`` -- many-to-many junction linking managers to sales reps.
- ``CustomerPriorityFlag`` -- audit trail of priority flags raised by managers.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from shared.logger import logger


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""

    pass


class UserRole(str, enum.Enum):
    """Enumeration of permitted user roles within the service."""

    sales_rep = "sales_rep"
    manager = "manager"
    administrator = "administrator"


class User(Base):
    """ORM model for the ``user`` table.

    Represents a service account.  The ``role`` column controls what
    operations the account may perform throughout the system.

    Public attributes:
    id             -- UUID primary key.
    name           -- display name.
    email          -- unique login address.
    hashed_password -- bcrypt (or equivalent) hash; never store plain text.
    role           -- one of ``sales_rep``, ``manager``, ``administrator``.
    is_active      -- soft-delete flag; defaults to ``True``.
    created_at     -- UTC timestamp set at insert time.
    """

    __tablename__ = "user"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="userrole"),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    # Relationships
    assigned_customers: Mapped[list["Customer"]] = relationship(
        "Customer",
        back_populates="assigned_rep",
        foreign_keys="Customer.assigned_rep_id",
    )
    manager_links: Mapped[list["ManagerRep"]] = relationship(
        "ManagerRep",
        foreign_keys="ManagerRep.manager_id",
        back_populates="manager",
    )
    rep_links: Mapped[list["ManagerRep"]] = relationship(
        "ManagerRep",
        foreign_keys="ManagerRep.rep_id",
        back_populates="rep",
    )
    priority_flags_raised: Mapped[list["CustomerPriorityFlag"]] = relationship(
        "CustomerPriorityFlag",
        back_populates="flagging_user",
    )

    def __repr__(self) -> str:
        """Return an unambiguous string representation of the User instance."""
        return f"<User id={self.id} email={self.email!r} role={self.role}>"


logger.debug("User model registered.")


class Customer(Base):
    """ORM model for the ``customer`` table.

    Stores customer details including optional geolocation coordinates and
    the sales rep currently assigned to the account.

    Public attributes:
    id              -- UUID primary key.
    name            -- customer or company name.
    address         -- full street address.
    lat             -- latitude; ``None`` if not yet geocoded.
    lng             -- longitude; ``None`` if not yet geocoded.
    is_active       -- soft-delete flag; defaults to ``True``.
    is_priority     -- elevated-attention flag; defaults to ``False``.
    assigned_rep_id -- FK to ``user.id``; ``None`` if unassigned.
    created_at      -- UTC timestamp set at insert time.
    """

    __tablename__ = "customer"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    address: Mapped[str] = mapped_column(String, nullable=False)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_priority: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    assigned_rep_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    # Relationships
    assigned_rep: Mapped["User | None"] = relationship(
        "User",
        back_populates="assigned_customers",
        foreign_keys=[assigned_rep_id],
    )
    priority_flags: Mapped[list["CustomerPriorityFlag"]] = relationship(
        "CustomerPriorityFlag",
        back_populates="customer",
    )

    def __repr__(self) -> str:
        """Return an unambiguous string representation of the Customer instance."""
        return f"<Customer id={self.id} name={self.name!r}>"


logger.debug("Customer model registered.")


class ManagerRep(Base):
    """ORM model for the ``manager_rep`` junction table.

    Represents the many-to-many relationship between managers and the
    sales reps that report to them.  Both columns are foreign keys to
    ``user.id``; the combination is unique to prevent duplicate links.

    Public attributes:
    manager_id -- FK to ``user.id`` for the manager side.
    rep_id     -- FK to ``user.id`` for the sales-rep side.
    """

    __tablename__ = "manager_rep"

    manager_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id"),
        primary_key=True,
    )
    rep_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id"),
        primary_key=True,
    )

    # Relationships
    manager: Mapped["User"] = relationship(
        "User",
        foreign_keys=[manager_id],
        back_populates="manager_links",
    )
    rep: Mapped["User"] = relationship(
        "User",
        foreign_keys=[rep_id],
        back_populates="rep_links",
    )

    def __repr__(self) -> str:
        """Return an unambiguous string representation of the ManagerRep instance."""
        return f"<ManagerRep manager_id={self.manager_id} rep_id={self.rep_id}>"


logger.debug("ManagerRep model registered.")


class CustomerPriorityFlag(Base):
    """ORM model for the ``customer_priority_flag`` table.

    Audit trail recording each time a manager raises the priority flag on
    a customer.  The ``flagged_by`` column must reference a user with the
    ``manager`` role — this constraint is enforced at the service layer.

    Public attributes:
    id          -- UUID primary key.
    customer_id -- FK to ``customer.id``.
    flagged_by  -- FK to ``user.id``; the manager who raised the flag.
    flagged_at  -- UTC timestamp of when the flag was raised.
    """

    __tablename__ = "customer_priority_flag"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customer.id"),
        nullable=False,
    )
    flagged_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id"),
        nullable=False,
    )
    flagged_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    # Relationships
    customer: Mapped["Customer"] = relationship(
        "Customer",
        back_populates="priority_flags",
    )
    flagging_user: Mapped["User"] = relationship(
        "User",
        back_populates="priority_flags_raised",
    )

    def __repr__(self) -> str:
        """Return an unambiguous string representation of the CustomerPriorityFlag."""
        return (
            f"<CustomerPriorityFlag id={self.id}"
            f" customer_id={self.customer_id}"
            f" flagged_by={self.flagged_by}>"
        )


logger.debug("CustomerPriorityFlag model registered.")
