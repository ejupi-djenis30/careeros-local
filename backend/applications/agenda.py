from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import cast

from pydantic import ValidationError
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from backend.applications.models import Application
from backend.applications.schemas import (
    ApplicationAgendaItem,
    ApplicationAgendaResponse,
    ApplicationNextAction,
    ApplicationStage,
    ApplicationTaskPriority,
)
from backend.applications.service import ApplicationValidationError
from backend.db.types import aware_utc

CLOSED_STAGES = ("rejected", "withdrawn", "archived")
VISIBLE_STATES = ("overdue", "today", "upcoming", "unscheduled", "needs_action")


class ApplicationAgendaService:
    """Build a private daily queue from scalar application projections."""

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _window(
        generated_at: datetime,
        local_day_end: datetime,
        horizon_days: int,
    ) -> tuple[datetime, datetime]:
        if generated_at.tzinfo is None:
            raise ApplicationValidationError("Agenda time must include a timezone")
        if local_day_end.tzinfo is None:
            raise ApplicationValidationError("Local day boundary must include a timezone")
        generated_at = generated_at.astimezone(timezone.utc)
        normalized_day_end = local_day_end.astimezone(timezone.utc)
        if normalized_day_end <= generated_at:
            raise ApplicationValidationError("Local day boundary must be in the future")
        if normalized_day_end > generated_at + timedelta(hours=26):
            raise ApplicationValidationError(
                "Local day boundary cannot be more than 26 hours ahead"
            )
        return normalized_day_end, generated_at + timedelta(days=horizon_days)

    @staticmethod
    def _next_action(row) -> ApplicationNextAction | None:
        values = (
            row.next_action_task_id,
            row.next_action_title,
            row.next_action_priority,
        )
        if all(value is None for value in values):
            if row.next_action_at is not None:
                raise ApplicationValidationError("Next-action projection is incomplete")
            return None
        if any(value is None for value in values):
            raise ApplicationValidationError("Next-action projection is incomplete")
        try:
            return ApplicationNextAction(
                id=row.next_action_task_id,
                title=row.next_action_title,
                due_at=aware_utc(row.next_action_at),
                priority=cast(ApplicationTaskPriority, row.next_action_priority),
            )
        except ValidationError as exc:
            raise ApplicationValidationError("Next-action projection is invalid") from exc

    @staticmethod
    def _state_expression(
        generated_at: datetime,
        today_end: datetime,
        horizon_end: datetime,
    ):
        identity_absent = and_(
            Application.next_action_task_id.is_(None),
            Application.next_action_title.is_(None),
            Application.next_action_priority.is_(None),
        )
        identity_incomplete = or_(
            Application.next_action_task_id.is_(None),
            Application.next_action_title.is_(None),
            Application.next_action_priority.is_(None),
        )
        return case(
            (
                and_(identity_absent, Application.next_action_at.is_(None)),
                "needs_action",
            ),
            (identity_incomplete, "invalid"),
            (
                Application.next_action_priority.notin_(
                    ("low", "normal", "high", "urgent")
                ),
                "invalid",
            ),
            (
                or_(
                    func.length(Application.next_action_task_id) == 0,
                    func.length(Application.next_action_title) == 0,
                ),
                "invalid",
            ),
            (Application.next_action_at.is_(None), "unscheduled"),
            (Application.next_action_at < generated_at, "overdue"),
            (Application.next_action_at < today_end, "today"),
            (Application.next_action_at <= horizon_end, "upcoming"),
            else_="later",
        )

    def build(
        self,
        user_id: int,
        *,
        local_day_end: datetime,
        horizon_days: int = 7,
        limit: int = 50,
        now: datetime | None = None,
    ) -> ApplicationAgendaResponse:
        if not 1 <= horizon_days <= 30:
            raise ApplicationValidationError("Agenda horizon must be between 1 and 30 days")
        if not 1 <= limit <= 200:
            raise ApplicationValidationError("Agenda limit must be between 1 and 200")

        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None:
            raise ApplicationValidationError("Agenda time must include a timezone")
        generated_at = instant.astimezone(timezone.utc)
        today_end, horizon_end = self._window(
            generated_at,
            local_day_end,
            horizon_days,
        )
        state_expression = self._state_expression(generated_at, today_end, horizon_end)
        classified = (
            select(
                Application.id.label("application_id"),
                Application.revision,
                Application.current_stage,
                Application.job_title,
                Application.job_company,
                Application.latest_event_at,
                Application.next_action_task_id,
                Application.next_action_title,
                Application.next_action_at,
                Application.next_action_priority,
                state_expression.label("agenda_state"),
            )
            .where(
                Application.user_id == user_id,
                Application.current_stage.notin_(CLOSED_STAGES),
            )
            .cte("agenda_classified")
        )

        state_order = case(
            *(
                (classified.c.agenda_state == state, rank)
                for rank, state in enumerate(VISIBLE_STATES)
            ),
            else_=len(VISIBLE_STATES),
        )
        priority_order = case(
            (classified.c.next_action_priority == "urgent", 0),
            (classified.c.next_action_priority == "high", 1),
            (classified.c.next_action_priority == "normal", 2),
            (classified.c.next_action_priority == "low", 3),
            else_=4,
        )
        item_order = (
            state_order,
            classified.c.next_action_at.asc(),
            priority_order,
            classified.c.latest_event_at.asc(),
            classified.c.application_id.asc(),
        )
        ranked = (
            select(
                *classified.c,
                func.row_number().over(order_by=item_order).label("agenda_rank"),
            )
            .where(classified.c.agenda_state.in_(VISIBLE_STATES))
            .cte("agenda_ranked")
        )
        stats = (
            select(
                func.count(classified.c.application_id).label("active_count"),
                func.coalesce(
                    func.sum(case((classified.c.agenda_state == "later", 1), else_=0)),
                    0,
                ).label("later_count"),
                func.coalesce(
                    func.sum(case((classified.c.agenda_state == "invalid", 1), else_=0)),
                    0,
                ).label("invalid_count"),
            )
            .select_from(classified)
            .cte("agenda_stats")
        )
        statement = (
            select(
                stats.c.active_count,
                stats.c.later_count,
                stats.c.invalid_count,
                *ranked.c,
            )
            .select_from(
                stats.outerjoin(
                    ranked,
                    ranked.c.agenda_rank <= limit,
                )
            )
            .order_by(ranked.c.agenda_rank.asc())
        )
        rows = self.db.execute(statement).all()
        stats_row = rows[0]
        invalid_count = int(stats_row.invalid_count)
        if invalid_count:
            raise ApplicationValidationError("Next-action projection is incomplete")

        items: list[ApplicationAgendaItem] = []
        for row in rows:
            if row.application_id is None:
                continue
            next_action = self._next_action(row)
            latest_event_at = aware_utc(row.latest_event_at)
            if latest_event_at is None:
                raise ApplicationValidationError("Application agenda is missing activity time")
            try:
                items.append(
                    ApplicationAgendaItem(
                        application_id=row.application_id,
                        application_revision=row.revision,
                        title=row.job_title,
                        company=row.job_company,
                        current_stage=cast(ApplicationStage, row.current_stage),
                        latest_event_at=latest_event_at,
                        state=row.agenda_state,
                        next_action=next_action,
                    )
                )
            except ValidationError as exc:
                raise ApplicationValidationError("Application agenda projection is invalid") from exc
        active_count = int(stats_row.active_count)
        later_count = int(stats_row.later_count)
        visible_count = active_count - later_count
        try:
            return ApplicationAgendaResponse(
                generated_at=generated_at,
                local_day_end=today_end,
                horizon_end=horizon_end,
                active_count=active_count,
                visible_count=visible_count,
                later_count=later_count,
                truncated_count=visible_count - len(items),
                items=items,
            )
        except ValidationError as exc:
            raise ApplicationValidationError("Application agenda response is invalid") from exc
