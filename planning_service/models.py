"""SQLAlchemy ORM models for the Planning Service.

Defines five database tables:

- ``DayPlan`` -- a sales rep's daily visit and call schedule.
- ``Visit`` -- an in-person customer visit within a day plan.
- ``Call`` -- a phone call to a customer within a day plan.
- ``Outbox`` -- transactional outbox for reliable event publishing.
- ``PlanReadModel`` -- denormalised read-side projection of a day plan.
"""

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from shared.logger import logger


class Base(DeclarativeBase):
    """Shared declarative base for all Planning Service ORM models."""

    pass


class DayPlanStatus(str, enum.Enum):
    """Enumeration of valid statuses for a day plan."""

    draft = "draft"
    confirmed = "confirmed"
    active = "active"
    completed = "completed"


class VisitStatus(str, enum.Enum):
    """Enumeration of valid statuses for a customer visit."""

    planned = "planned"
    in_progress = "in_progress"
    completed = "completed"
    missed = "missed"
    rescheduled = "rescheduled"


class CallStatus(str, enum.Enum):
    """Enumeration of valid statuses for a customer call."""

    scheduled = "scheduled"
    attempted = "attempted"
    completed = "completed"


class DayPlan(Base):
    """ORM model for the ``day_plan`` table.

    Represents a sales rep's full schedule for a single working day,
    including an optional mapped route.

    Public attributes:
    id             -- UUID primary key.
    rep_id         -- UUID of the assigned sales rep (no cross-service FK).
    status         -- one of ``draft``, ``confirmed``, ``active``, ``completed``.
    start_location -- optional free-text starting address.
    end_location   -- optional free-text ending address.
    map_url        -- optional URL for the generated route map.
    date           -- calendar date this plan covers.
    created_at     -- UTC timestamp set at insert time.
    """

    __tablename__ = "day_plan"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    rep_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    status: Mapped[DayPlanStatus] = mapped_column(
        SAEnum(DayPlanStatus, name="dayplanstatus"),
        nullable=False,
        default=DayPlanStatus.draft,
    )
    start_location: Mapped[str | None] = mapped_column(String, nullable=True)
    end_location: Mapped[str | None] = mapped_column(String, nullable=True)
    map_url: Mapped[str | None] = mapped_column(String, nullable=True)
    date: Mapped[datetime] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    # Relationships
    visits: Mapped[list["Visit"]] = relationship(
        "Visit",
        back_populates="plan",
    )
    calls: Mapped[list["Call"]] = relationship(
        "Call",
        back_populates="plan",
    )

    def __repr__(self) -> str:
        """Return an unambiguous string representation of the DayPlan instance."""
        return f"<DayPlan id={self.id} rep_id={self.rep_id} date={self.date}>"


logger.debug("DayPlan model registered.")


class Visit(Base):
    """ORM model for the ``visit`` table.

    Represents a single in-person customer visit scheduled within a day plan.
    The ``customer_name`` field is denormalised to avoid cross-service joins.

    Public attributes:
    id               -- UUID primary key.
    plan_id          -- FK to ``day_plan.id``.
    customer_id      -- UUID of the customer (no cross-service FK).
    customer_name    -- denormalised display name of the customer.
    status           -- one of ``planned``, ``in_progress``, ``completed``,
                        ``missed``, ``rescheduled``.
    outcome_notes    -- optional free-text notes recorded after the visit.
    scheduled_order  -- integer position in the day's visit sequence.
    created_at       -- UTC timestamp set at insert time.
    """

    __tablename__ = "visit"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("day_plan.id"),
        nullable=False,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    customer_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[VisitStatus] = mapped_column(
        SAEnum(VisitStatus, name="visitstatus"),
        nullable=False,
        default=VisitStatus.planned,
    )
    outcome_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    scheduled_order: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    # Relationships
    plan: Mapped["DayPlan"] = relationship("DayPlan", back_populates="visits")

    def __repr__(self) -> str:
        """Return an unambiguous string representation of the Visit instance."""
        return (
            f"<Visit id={self.id}"
            f" plan_id={self.plan_id}"
            f" customer_id={self.customer_id}>"
        )


logger.debug("Visit model registered.")


class Call(Base):
    """ORM model for the ``call`` table.

    Represents a scheduled phone call to a customer within a day plan.
    The ``customer_name`` field is denormalised to avoid cross-service joins.

    Public attributes:
    id               -- UUID primary key.
    plan_id          -- FK to ``day_plan.id``.
    customer_id      -- UUID of the customer (no cross-service FK).
    customer_name    -- denormalised display name of the customer.
    status           -- one of ``scheduled``, ``attempted``, ``completed``.
    outcome_notes    -- optional free-text notes recorded after the call.
    duration_minutes -- planned call duration in minutes; defaults to ``30``.
    created_at       -- UTC timestamp set at insert time.
    """

    __tablename__ = "call"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("day_plan.id"),
        nullable=False,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    customer_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[CallStatus] = mapped_column(
        SAEnum(CallStatus, name="callstatus"),
        nullable=False,
        default=CallStatus.scheduled,
    )
    outcome_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=30,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    # Relationships
    plan: Mapped["DayPlan"] = relationship("DayPlan", back_populates="calls")

    def __repr__(self) -> str:
        """Return an unambiguous string representation of the Call instance."""
        return (
            f"<Call id={self.id}"
            f" plan_id={self.plan_id}"
            f" customer_id={self.customer_id}>"
        )


logger.debug("Call model registered.")


class Outbox(Base):
    """ORM model for the ``outbox`` table.

    Stores events that must be reliably published to the message broker.
    A background process polls for rows where ``published`` is ``False``
    and publishes them, then marks them as published.

    Public attributes:
    id           -- UUID primary key.
    event_type   -- string identifier for the event (e.g. ``plan.confirmed``).
    aggregate_id -- UUID of the aggregate that raised the event.
    payload      -- JSON body of the event.
    published    -- ``False`` until the event is delivered to the broker.
    created_at   -- UTC timestamp set at insert time.
    """

    __tablename__ = "outbox"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    published: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    def __repr__(self) -> str:
        """Return an unambiguous string representation of the Outbox instance."""
        return (
            f"<Outbox id={self.id}"
            f" event_type={self.event_type!r}"
            f" published={self.published}>"
        )


logger.debug("Outbox model registered.")


class PlanReadModel(Base):
    """ORM model for the ``plan_read_model`` table.

    Denormalised read-side projection of a day plan, maintained by event
    handlers.  Used to serve list and summary queries without joining the
    write-side tables.

    Public attributes:
    id          -- UUID primary key.
    rep_id      -- UUID of the sales rep.
    status      -- current status string.
    date        -- calendar date the plan covers.
    visit_count -- number of visits in the plan.
    call_count  -- number of calls in the plan.
    created_at  -- UTC timestamp when the projection was first created.
    updated_at  -- UTC timestamp of the most recent projection update.
    """

    __tablename__ = "plan_read_model"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    rep_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String, nullable=False)
    date: Mapped[datetime] = mapped_column(Date, nullable=False)
    visit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    def __repr__(self) -> str:
        """Return an unambiguous string representation of the PlanReadModel instance."""
        return (
            f"<PlanReadModel id={self.id}"
            f" rep_id={self.rep_id}"
            f" date={self.date}>"
        )


logger.debug("PlanReadModel model registered.")
