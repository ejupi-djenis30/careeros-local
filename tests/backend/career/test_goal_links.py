from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.career.goal_schemas import CareerGoalPayload
from backend.career.schemas import CareerProfileWrite
from backend.career.service import CareerProfileService
from backend.resumes.models import ResumeDraft, ResumeVersion
from backend.resumes.service import ResumeService


def _actions(version_id: str) -> list[dict]:
    return [
        {
            "id": "learn-architecture",
            "title": "Complete architecture course",
            "kind": "learning",
        },
        {
            "id": "update-resume",
            "title": "Update resume",
            "kind": "portfolio",
            "linked_learning_activity_ids": ["learn-architecture"],
            "linked_resume_version_ids": [version_id],
        },
    ]


def test_goal_links_require_learning_actions_in_the_same_goal() -> None:
    payload = CareerGoalPayload.model_validate(
        {"actions": _actions("version-1")}
    )
    assert payload.actions[1].linked_learning_activity_ids == ["learn-architecture"]

    invalid = _actions("version-1")
    invalid[1]["linked_learning_activity_ids"] = ["missing-course"]
    with pytest.raises(ValidationError, match="same goal"):
        CareerGoalPayload.model_validate({"actions": invalid})


def test_profile_goal_links_only_owned_resume_versions(
    db_session, test_user
) -> None:
    profile_service = CareerProfileService(db_session)
    profile = profile_service.save(
        test_user.id,
        CareerProfileWrite(display_name="Ada", facts=[], goals=[]),
    )
    draft = ResumeDraft(
        profile_id=profile.id,
        revision=1,
        profile_revision=profile.revision,
        title="CV Staff",
        template_kind="ats",
        section_config={},
        selected_fact_ids=[],
        content_overrides={},
        canvas_document={},
        generation_context={},
    )
    db_session.add(draft)
    db_session.flush()
    version = ResumeVersion(
        draft_id=draft.id,
        version_number=1,
        semantic_version="1.0.0",
        snapshot={},
        snapshot_sha256="a" * 64,
        profile_revision=profile.revision,
        selected_fact_ids=[],
        template_kind="ats",
        renderer_version="test",
        published_at=datetime.now(timezone.utc),
        quality_report={},
    )
    db_session.add(version)
    db_session.commit()

    saved = profile_service.save(
        test_user.id,
        CareerProfileWrite(
            expected_revision=profile.revision,
            display_name="Ada",
            facts=[],
            goals=[
                {
                    "name": "Staff role",
                    "payload": {"actions": _actions(version.id)},
                }
            ],
        ),
    )
    assert saved.goals[0].payload["actions"][1]["linked_resume_version_ids"] == [
        version.id
    ]
    options = ResumeService(db_session).list_versions(test_user.id)
    assert [(item.id, item.draft_title) for item in options] == [
        (version.id, "CV Staff")
    ]

    with pytest.raises(ValueError, match="same career profile"):
        profile_service.save(
            test_user.id,
            CareerProfileWrite(
                expected_revision=saved.revision,
                display_name="Ada",
                facts=[],
                goals=[
                    {
                        "name": "Staff role",
                        "payload": {"actions": _actions("missing-version")},
                    }
                ],
            ),
        )
