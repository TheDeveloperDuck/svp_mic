"""Pydantic request and response schemas for the Planning Service.

Each database model has a paired ``Create`` schema (used for inbound
request validation) and a ``Response`` schema (used to serialise outbound
data).  Response schemas are configured with ``from_attributes=True`` so
they can be built directly from SQLAlchemy ORM instances.

Exported schemas:
- DayPlanCreate, DayPlanResponse
- VisitCreate, VisitResponse
- CallCreate, CallResponse
- PlanReadModelResponse
"""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from planning_service.models import CallStatus, DayPlanStatus, VisitStatus
from shared.logger import logger


# ---------------------------------------------------------------------------
# DayPlan
# ---------------------------------------------------------------------------

class DayPlanCreate(BaseModel):
    """Schema for creating a new day plan.

    Fields:
    rep_id         -- UUID of the sales rep this plan belongs to.
    date           -- calendar date the plan covers.
    start_location -- optional free-text starting address.
    end_location   -- optional free-text ending address.
    """

    rep_id: UUID
    date: date
    start_location: str | None = None
    end_location: str | None = None


class DayPlanResponse(BaseModel):
    """Schema for serialising a day plan in API responses.

    Fields:
    id             -- UUID primary key.
    rep_id         -- UUID of the assigned sales rep.
    status         -- current plan status.
    start_location -- optional starting address.
    end_location   -- optional ending address.
    map_url        -- optional URL for the generated route map.
    date           -- calendar date this plan covers.
    created_at     -- UTC creation timestamp.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rep_id: UUID
    status: DayPlanStatus
    start_location: str | None
    end_location: str | None
    map_url: str | None
    date: date
    created_at: datetime


logger.debug("DayPlan schemas loaded.")


# ---------------------------------------------------------------------------
# Visit
# ---------------------------------------------------------------------------

class VisitCreate(BaseModel):
    """Schema for creating a new customer visit within a day plan.

    Fields:
    plan_id         -- UUID of the parent day plan.
    customer_id     -- UUID of the customer to visit.
    customer_name   -- denormalised display name of the customer.
    scheduled_order -- integer position in the day's visit sequence.
    """

    plan_id: UUID
    customer_id: UUID
    customer_name: str
    scheduled_order: int


class VisitResponse(BaseModel):
    """Schema for serialising a visit record in API responses.

    Fields:
    id              -- UUID primary key.
    plan_id         -- UUID of the parent day plan.
    customer_id     -- UUID of the customer.
    customer_name   -- denormalised display name of the customer.
    status          -- current visit status.
    outcome_notes   -- optional notes recorded after the visit.
    scheduled_order -- position in the day's visit sequence.
    created_at      -- UTC creation timestamp.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_id: UUID
    customer_id: UUID
    customer_name: str
    status: VisitStatus
    outcome_notes: str | None
    scheduled_order: int
    created_at: datetime


logger.debug("Visit schemas loaded.")


# ---------------------------------------------------------------------------
# Call
# ---------------------------------------------------------------------------

class CallCreate(BaseModel):
    """Schema for creating a new customer call within a day plan.

    Fields:
    plan_id          -- UUID of the parent day plan.
    customer_id      -- UUID of the customer to call.
    customer_name    -- denormalised display name of the customer.
    duration_minutes -- planned call duration in minutes; defaults to ``30``.
    """

    plan_id: UUID
    customer_id: UUID
    customer_name: str
    duration_minutes: int = 30


class CallResponse(BaseModel):
    """Schema for serialising a call record in API responses.

    Fields:
    id               -- UUID primary key.
    plan_id          -- UUID of the parent day plan.
    customer_id      -- UUID of the customer.
    customer_name    -- denormalised display name of the customer.
    status           -- current call status.
    outcome_notes    -- optional notes recorded after the call.
    duration_minutes -- planned call duration in minutes.
    created_at       -- UTC creation timestamp.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_id: UUID
    customer_id: UUID
    customer_name: str
    status: CallStatus
    outcome_notes: str | None
    duration_minutes: int
    created_at: datetime


logger.debug("Call schemas loaded.")


# ---------------------------------------------------------------------------
# PlanReadModel
# ---------------------------------------------------------------------------

class PlanReadModelResponse(BaseModel):
    """Schema for serialising a plan read-model row.

    Fields:
    id          -- UUID primary key.
    rep_id      -- UUID of the sales rep.
    status      -- current plan status string.
    date        -- calendar date the plan covers.
    visit_count -- number of visits in the plan.
    call_count  -- number of calls in the plan.
    updated_at  -- UTC timestamp of the last update.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rep_id: UUID
    status: str
    date: date
    visit_count: int
    call_count: int
    updated_at: datetime


logger.debug("PlanReadModel schemas loaded.")
