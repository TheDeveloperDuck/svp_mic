"""User CRUD router for the Customer User Service.

Endpoints:
- GET    /users              -- list all users.
- GET    /users/{user_id}   -- fetch a single user by ID.
- POST   /users             -- create a new user account.
- PATCH  /users/{user_id}   -- update user fields.
- DELETE /users/{user_id}   -- hard-delete a user (administrator only).
"""

from typing import Annotated
from uuid import UUID

import bcrypt
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from customer_user_service.database import get_db
from customer_user_service.models import User, UserRole
from customer_user_service.schemas import UserCreate, UserResponse
from shared.logger import logger


# ---------------------------------------------------------------------------
# Local schemas (not in schemas.py — partial update shapes)
# ---------------------------------------------------------------------------

class UserUpdate(BaseModel):
    """Schema for partially updating a user account.

    All fields are optional; only supplied fields are applied.

    Fields:
    name  -- updated display name.
    email -- updated login address.
    role  -- updated role assignment.
    """

    name: str | None = None
    email: EmailStr | None = None
    role: UserRole | None = None


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/users", tags=["users"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_user_or_404(user_id: UUID, db: AsyncSession) -> User:
    """Return the user with the given ID or raise HTTP 404.

    Arguments:
    user_id -- UUID of the user to fetch.
    db      -- active database session.

    Return value:
    User -- the matching ORM instance.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found.",
        )
    return user


async def _require_administrator(
    x_user_id: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Validate that the requesting user holds the administrator role.

    Reads the ``X-User-Id`` header and fetches the corresponding user from
    the database.  Raises HTTP 403 if the header is absent, the UUID is
    malformed, or the user does not hold the ``administrator`` role.

    Arguments:
    x_user_id -- raw UUID string from the ``X-User-Id`` request header.
    db        -- active database session.

    Return value:
    User -- the validated administrator.
    """
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
    if user is None or user.role != UserRole.administrator:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires the administrator role.",
        )
    return user


def _hash_password(plain: str) -> str:
    """Return a bcrypt hash of the supplied plain-text password.

    Arguments:
    plain -- the plain-text password to hash.

    Return value:
    str -- the bcrypt-hashed password string.
    """
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=list[UserResponse])
async def list_users(
    db: AsyncSession = Depends(get_db),
) -> list[UserResponse]:
    """Return all user accounts.

    Return value:
    list[UserResponse] -- all user records in the database.
    """
    result = await db.execute(select(User))
    users = result.scalars().all()
    logger.debug("list_users returned %d records.", len(users))
    return [UserResponse.model_validate(u) for u in users]


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Return a single user by ID.

    Arguments:
    user_id -- UUID of the user to fetch.

    Return value:
    UserResponse -- the matching user record.
    """
    user = await _get_user_or_404(user_id, db)
    return UserResponse.model_validate(user)


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Create a new user account.

    Hashes the plain-text password from the request before persisting.
    Raises HTTP 409 if the email address is already in use.

    Arguments:
    payload -- validated user creation data.

    Return value:
    UserResponse -- the newly created user record.
    """
    existing = await db.execute(
        select(User).where(User.email == payload.email)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Email address {payload.email!r} is already registered.",
        )

    user = User(
        name=payload.name,
        email=payload.email,
        hashed_password=_hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.debug("User created: %s (%s).", user.id, user.role)
    return UserResponse.model_validate(user)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Update mutable fields on an existing user account.

    Only fields included in the request body are applied; omitted fields
    are left unchanged.

    Arguments:
    user_id -- UUID of the user to update.
    payload -- partial update data.

    Return value:
    UserResponse -- the updated user record.
    """
    user = await _get_user_or_404(user_id, db)

    if payload.email is not None and payload.email != user.email:
        clash = await db.execute(
            select(User).where(User.email == payload.email)
        )
        if clash.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Email address {payload.email!r} is already registered."
                ),
            )

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    logger.debug("User updated: %s.", user_id)
    return UserResponse.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    _admin: Annotated[User, Depends(_require_administrator)],
    db: AsyncSession = Depends(get_db),
) -> None:
    """Hard-delete a user account (administrator only).

    Requires the ``X-User-Id`` header to belong to a user with the
    ``administrator`` role.

    Arguments:
    user_id -- UUID of the user to delete.
    _admin  -- resolved administrator (validated via ``X-User-Id``).
    """
    user = await _get_user_or_404(user_id, db)
    await db.delete(user)
    await db.commit()
    logger.info("User hard-deleted: %s.", user_id)
