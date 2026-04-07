"""Customer CRUD router for the Customer User Service.

Endpoints:
- GET  /customers                        -- list all active customers (cached).
- GET  /customers/{customer_id}          -- fetch a single customer by ID.
- POST /customers                        -- create a new customer.
- PATCH /customers/{customer_id}         -- update customer fields.
- PATCH /customers/{customer_id}/deactivate -- soft-delete a customer.
- PATCH /customers/{customer_id}/flag    -- set the priority flag (manager only).
- PATCH /customers/{customer_id}/assign  -- assign a sales rep to a customer.
"""

import json
import os
from typing import Annotated
from uuid import UUID

import redis.asyncio as redis
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from customer_user_service.database import get_db
from customer_user_service.models import (
    Customer,
    CustomerPriorityFlag,
    User,
    UserRole,
)
from customer_user_service.producers.customer_deactivated import (
    publish_customer_deactivated,
)
from customer_user_service.schemas import CustomerCreate, CustomerResponse
from shared.exceptions import CustomerDeactivatedError
from shared.logger import logger


# ---------------------------------------------------------------------------
# Redis client
# ---------------------------------------------------------------------------

_REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
_redis: redis.Redis = redis.from_url(_REDIS_URL, decode_responses=True)
_ACTIVE_CUSTOMERS_KEY = "active_customers"


# ---------------------------------------------------------------------------
# Local schemas (not in schemas.py — partial update shapes)
# ---------------------------------------------------------------------------

class CustomerUpdate(BaseModel):
    """Schema for partially updating a customer record.

    All fields are optional; only supplied fields are applied.

    Fields:
    name            -- updated customer or company name.
    address         -- updated full street address.
    lat             -- updated latitude; pass ``None`` to clear.
    lng             -- updated longitude; pass ``None`` to clear.
    assigned_rep_id -- updated sales rep assignment; pass ``None`` to unassign.
    """

    name: str | None = None
    address: str | None = None
    lat: float | None = None
    lng: float | None = None
    assigned_rep_id: UUID | None = None


class AssignRepRequest(BaseModel):
    """Schema for assigning a sales rep to a customer.

    Fields:
    rep_id -- UUID of the sales rep to assign.
    """

    rep_id: UUID


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/customers", tags=["customers"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_customer_or_404(
    customer_id: UUID,
    db: AsyncSession,
) -> Customer:
    """Return the customer with the given ID or raise HTTP 404.

    Arguments:
    customer_id -- UUID of the customer to fetch.
    db          -- active database session.

    Return value:
    Customer -- the matching ORM instance.
    """
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found.",
        )
    return customer


def _require_role(required_role: UserRole):
    """Return a FastAPI dependency that enforces a minimum user role.

    Reads the ``X-User-Id`` header, fetches the user from the database,
    and raises HTTP 403 if the user is missing or does not hold the
    required role.

    Arguments:
    required_role -- the ``UserRole`` value the caller must possess.

    Return value:
    Callable -- an async FastAPI dependency yielding the validated ``User``.
    """
    async def _check(
        x_user_id: Annotated[str | None, Header()] = None,
        db: AsyncSession = Depends(get_db),
    ) -> User:
        """Validate that the requesting user holds the required role."""
        if not x_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="X-User-Id header is required.",
            )
        try:
            user_uuid = UUID(x_user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="X-User-Id must be a valid UUID.",
            )
        result = await db.execute(select(User).where(User.id == user_uuid))
        user = result.scalar_one_or_none()
        if user is None or user.role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"This action requires the {required_role.value} role."
                ),
            )
        return user

    return _check


async def _invalidate_cache() -> None:
    """Delete the active customers cache entry from Redis.

    Failures are logged and swallowed so a Redis outage does not break
    write operations.
    """
    try:
        await _redis.delete(_ACTIVE_CUSTOMERS_KEY)
        logger.debug("Active customers cache invalidated.")
    except Exception as exc:
        logger.warning("Cache invalidation failed: %s", exc)


async def _read_cache() -> list[dict] | None:
    """Return the cached active customers list or ``None`` on a miss.

    Return value:
    list[dict] -- deserialised list of customer dicts, or ``None``.
    """
    try:
        raw = await _redis.get(_ACTIVE_CUSTOMERS_KEY)
        if raw:
            logger.debug("Active customers served from cache.")
            return json.loads(raw)
    except Exception as exc:
        logger.warning("Cache read failed: %s", exc)
    return None


async def _write_cache(records: list[CustomerResponse]) -> None:
    """Serialise and store the active customers list in Redis.

    Arguments:
    records -- list of ``CustomerResponse`` instances to cache.
    """
    try:
        payload = json.dumps([r.model_dump(mode="json") for r in records])
        await _redis.set(_ACTIVE_CUSTOMERS_KEY, payload)
        logger.debug(
            "Active customers cache populated (%d records).", len(records)
        )
    except Exception as exc:
        logger.warning("Cache write failed: %s", exc)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=list[CustomerResponse])
async def list_customers(
    db: AsyncSession = Depends(get_db),
) -> list[CustomerResponse]:
    """Return all active customers.

    Checks Redis for a cached result first.  On a cache miss, queries the
    database and repopulates the cache before returning.

    Return value:
    list[CustomerResponse] -- active customer records.
    """
    cached = await _read_cache()
    if cached is not None:
        return [CustomerResponse.model_validate(item) for item in cached]

    result = await db.execute(
        select(Customer).where(Customer.is_active == True)  # noqa: E712
    )
    customers = result.scalars().all()
    response = [CustomerResponse.model_validate(c) for c in customers]
    await _write_cache(response)
    return response


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> CustomerResponse:
    """Return a single customer by ID.

    Arguments:
    customer_id -- UUID of the customer to fetch.

    Return value:
    CustomerResponse -- the matching customer record.
    """
    customer = await _get_customer_or_404(customer_id, db)
    return CustomerResponse.model_validate(customer)


@router.post(
    "",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_customer(
    payload: CustomerCreate,
    db: AsyncSession = Depends(get_db),
) -> CustomerResponse:
    """Create a new customer record.

    Invalidates the active customers cache on success.

    Arguments:
    payload -- validated customer creation data.

    Return value:
    CustomerResponse -- the newly created customer record.
    """
    customer = Customer(**payload.model_dump())
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    await _invalidate_cache()
    logger.debug("Customer created: %s.", customer.id)
    return CustomerResponse.model_validate(customer)


@router.patch("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: UUID,
    payload: CustomerUpdate,
    db: AsyncSession = Depends(get_db),
) -> CustomerResponse:
    """Update mutable fields on an existing customer record.

    Only fields included in the request body are applied; omitted fields
    are left unchanged.  Invalidates the active customers cache on success.

    Arguments:
    customer_id -- UUID of the customer to update.
    payload     -- partial update data.

    Return value:
    CustomerResponse -- the updated customer record.
    """
    customer = await _get_customer_or_404(customer_id, db)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(customer, field, value)
    await db.commit()
    await db.refresh(customer)
    await _invalidate_cache()
    logger.debug("Customer updated: %s.", customer_id)
    return CustomerResponse.model_validate(customer)


@router.patch("/{customer_id}/deactivate", response_model=CustomerResponse)
async def deactivate_customer(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> CustomerResponse:
    """Soft-delete a customer by setting ``is_active`` to ``False``.

    Invalidates the active customers cache and fires a
    ``customer.deactivated`` Kafka event on success.

    Arguments:
    customer_id -- UUID of the customer to deactivate.

    Return value:
    CustomerResponse -- the deactivated customer record.
    """
    customer = await _get_customer_or_404(customer_id, db)

    try:
        if not customer.is_active:
            raise CustomerDeactivatedError(
                f"Customer {customer_id} is already deactivated."
            )
    except CustomerDeactivatedError as exc:
        logger.warning(str(exc))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    customer.is_active = False
    await db.commit()
    await db.refresh(customer)
    await _invalidate_cache()
    logger.info("Customer deactivated: %s.", customer_id)

    await publish_customer_deactivated(str(customer_id))

    return CustomerResponse.model_validate(customer)


@router.patch("/{customer_id}/flag", response_model=CustomerResponse)
async def flag_customer(
    customer_id: UUID,
    manager: Annotated[User, Depends(_require_role(UserRole.manager))],
    db: AsyncSession = Depends(get_db),
) -> CustomerResponse:
    """Set the priority flag on a customer (manager only).

    Records an audit entry in ``customer_priority_flag`` and sets
    ``is_priority`` to ``True`` on the customer record.

    Arguments:
    customer_id -- UUID of the customer to flag.
    manager     -- the authenticated manager (resolved via ``X-User-Id``).

    Return value:
    CustomerResponse -- the updated customer record.
    """
    customer = await _get_customer_or_404(customer_id, db)
    customer.is_priority = True

    flag = CustomerPriorityFlag(
        customer_id=customer.id,
        flagged_by=manager.id,
    )
    db.add(flag)
    await db.commit()
    await db.refresh(customer)
    logger.info(
        "Customer %s flagged as priority by manager %s.",
        customer_id,
        manager.id,
    )
    return CustomerResponse.model_validate(customer)


@router.patch("/{customer_id}/assign", response_model=CustomerResponse)
async def assign_rep(
    customer_id: UUID,
    payload: AssignRepRequest,
    db: AsyncSession = Depends(get_db),
) -> CustomerResponse:
    """Assign a sales rep to a customer.

    Verifies that the target user exists and holds the ``sales_rep`` role
    before applying the assignment.

    Arguments:
    customer_id -- UUID of the customer to update.
    payload     -- request body containing the rep's UUID.

    Return value:
    CustomerResponse -- the updated customer record.
    """
    customer = await _get_customer_or_404(customer_id, db)

    rep_result = await db.execute(
        select(User).where(User.id == payload.rep_id)
    )
    rep = rep_result.scalar_one_or_none()
    if rep is None or rep.role != UserRole.sales_rep:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User {payload.rep_id} is not an active sales rep.",
        )

    customer.assigned_rep_id = rep.id
    await db.commit()
    await db.refresh(customer)
    logger.debug(
        "Customer %s assigned to rep %s.", customer_id, payload.rep_id
    )
    return CustomerResponse.model_validate(customer)
