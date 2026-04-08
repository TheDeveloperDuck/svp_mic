"""Saga orchestrator for the Planning Service.

Exposes one async function:
- confirm_plan -- confirm a plan and write the outbox event atomically.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planning_service.models import (
    Call,
    DayPlan,
    DayPlanStatus,
    Outbox,
    Visit,
)
from shared.exceptions import PlanConfirmationError
from shared.logger import logger


async def confirm_plan(plan_id: UUID, db: AsyncSession) -> None:
    """Confirm a plan and write a plan.confirmed outbox row atomically.

    Transitions the plan from ``draft`` to ``confirmed`` and writes a
    ``plan.confirmed`` outbox row within a single database transaction.
    The outbox payload includes the plan ID and the deduplicated list
    of customer IDs drawn from all visits and calls on the plan.

    If the plan update or outbox write fails, the transaction is rolled
    back and ``PlanConfirmationError`` is raised.

    Arguments:
    plan_id -- UUID of the plan to confirm.
    db      -- active database session.

    Raises:
    PlanConfirmationError -- if the plan is not found, is not in
        ``draft`` status, or the transaction fails.
    """
    try:
        result = await db.execute(
            select(DayPlan).where(DayPlan.id == plan_id)
        )
        plan = result.scalar_one_or_none()
        if plan is None:
            raise PlanConfirmationError(f"Plan {plan_id} not found.")

        if plan.status != DayPlanStatus.draft:
            raise PlanConfirmationError(
                f"Plan {plan_id} is not in draft status"
                f" (current: '{plan.status}')."
            )

        visits_result = await db.execute(
            select(Visit).where(Visit.plan_id == plan_id)
        )
        calls_result = await db.execute(
            select(Call).where(Call.plan_id == plan_id)
        )
        visits = list(visits_result.scalars().all())
        calls = list(calls_result.scalars().all())

        customer_ids: list[str] = list(
            {str(v.customer_id) for v in visits}
            | {str(c.customer_id) for c in calls}
        )

        plan.status = DayPlanStatus.confirmed

        outbox_row = Outbox(
            event_type="plan.confirmed",
            aggregate_id=plan_id,
            payload={
                "plan_id": str(plan_id),
                "customer_ids": customer_ids,
            },
        )
        db.add(outbox_row)

        await db.commit()
        logger.info(
            "Plan %s confirmed; outbox event written (%d customer(s)).",
            plan_id,
            len(customer_ids),
        )

    except PlanConfirmationError:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        logger.error("Failed to confirm plan %s: %s.", plan_id, exc)
        raise PlanConfirmationError(
            f"Failed to confirm plan {plan_id}: {exc}"
        ) from exc
