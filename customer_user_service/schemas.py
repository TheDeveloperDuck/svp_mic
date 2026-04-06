"""Pydantic request and response schemas for the Customer User Service.

Each database model has a paired ``Create`` schema (used for inbound
request validation) and a ``Response`` schema (used to serialise outbound
data).  Response schemas are configured with ``from_attributes=True`` so
they can be built directly from SQLAlchemy ORM instances.

Exported schemas:
- UserCreate, UserResponse
- CustomerCreate, CustomerResponse
- ManagerRepCreate, ManagerRepResponse
- CustomerPriorityFlagCreate, CustomerPriorityFlagResponse
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr

from customer_user_service.models import UserRole
from shared.logger import logger


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    """Schema for creating a new user account.

    The ``password`` field accepts a plain-text value; the router or
    service layer is responsible for hashing it before persistence.

    Fields:
    name     -- display name for the account.
    email    -- unique login address.
    password -- plain-text password (hashed before storage).
    role     -- one of ``sales_rep``, ``manager``, ``administrator``.
    """

    name: str
    email: EmailStr
    password: str
    role: UserRole


class UserResponse(BaseModel):
    """Schema for serialising a user record in API responses.

    Fields:
    id         -- UUID primary key.
    name       -- display name.
    email      -- login address.
    role       -- assigned role.
    is_active  -- whether the account is active.
    created_at -- UTC creation timestamp.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: EmailStr
    role: UserRole
    is_active: bool
    created_at: datetime


logger.debug("User schemas loaded.")


# ---------------------------------------------------------------------------
# Customer
# ---------------------------------------------------------------------------

class CustomerCreate(BaseModel):
    """Schema for creating a new customer record.

    Fields:
    name            -- customer or company name.
    address         -- full street address.
    lat             -- latitude coordinate; omit if not yet geocoded.
    lng             -- longitude coordinate; omit if not yet geocoded.
    is_priority     -- set to ``True`` to mark as a priority account.
    assigned_rep_id -- UUID of the sales rep to assign; omit if unassigned.
    """

    name: str
    address: str
    lat: float | None = None
    lng: float | None = None
    is_priority: bool = False
    assigned_rep_id: UUID | None = None


class CustomerResponse(BaseModel):
    """Schema for serialising a customer record in API responses.

    Fields:
    id              -- UUID primary key.
    name            -- customer or company name.
    address         -- full street address.
    lat             -- latitude; ``None`` if not geocoded.
    lng             -- longitude; ``None`` if not geocoded.
    is_active       -- soft-delete flag.
    is_priority     -- elevated-attention flag.
    assigned_rep_id -- UUID of the assigned sales rep; ``None`` if unassigned.
    created_at      -- UTC creation timestamp.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    address: str
    lat: float | None
    lng: float | None
    is_active: bool
    is_priority: bool
    assigned_rep_id: UUID | None
    created_at: datetime


logger.debug("Customer schemas loaded.")


# ---------------------------------------------------------------------------
# ManagerRep
# ---------------------------------------------------------------------------

class ManagerRepCreate(BaseModel):
    """Schema for creating a manager-to-rep assignment.

    Both IDs must reference existing ``User`` records.  The caller is
    responsible for ensuring ``manager_id`` belongs to a user with the
    ``manager`` role.

    Fields:
    manager_id -- UUID of the manager.
    rep_id     -- UUID of the sales rep.
    """

    manager_id: UUID
    rep_id: UUID


class ManagerRepResponse(BaseModel):
    """Schema for serialising a manager-rep assignment in API responses.

    Fields:
    manager_id -- UUID of the manager.
    rep_id     -- UUID of the sales rep.
    """

    model_config = ConfigDict(from_attributes=True)

    manager_id: UUID
    rep_id: UUID


logger.debug("ManagerRep schemas loaded.")


# ---------------------------------------------------------------------------
# CustomerPriorityFlag
# ---------------------------------------------------------------------------

class CustomerPriorityFlagCreate(BaseModel):
    """Schema for raising a priority flag on a customer.

    The ``flagged_by`` user must hold the ``manager`` role; this
    constraint is enforced at the service layer, not here.

    Fields:
    customer_id -- UUID of the customer being flagged.
    flagged_by  -- UUID of the manager raising the flag.
    """

    customer_id: UUID
    flagged_by: UUID


class CustomerPriorityFlagResponse(BaseModel):
    """Schema for serialising a priority flag record in API responses.

    Fields:
    id          -- UUID primary key.
    customer_id -- UUID of the flagged customer.
    flagged_by  -- UUID of the manager who raised the flag.
    flagged_at  -- UTC timestamp of when the flag was raised.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID
    flagged_by: UUID
    flagged_at: datetime


logger.debug("CustomerPriorityFlag schemas loaded.")
