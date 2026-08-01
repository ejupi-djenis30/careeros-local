"""Quiesce user-owned background activity before vault maintenance."""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.models import SearchProfile
from backend.services.scheduler import remove_schedules_for_profiles
from backend.services.search_status import cancel_and_clear_tasks


def owned_search_profile_ids(db: Session, user_id: int) -> list[int]:
    return [
        int(profile_id)
        for (profile_id,) in db.query(SearchProfile.id)
        .filter(SearchProfile.user_id == user_id)
        .all()
    ]


async def quiesce_user_vault_activity(db: Session, user_id: int) -> None:
    profile_ids = owned_search_profile_ids(db, user_id)
    remove_schedules_for_profiles(profile_ids)
    await cancel_and_clear_tasks(profile_ids)
