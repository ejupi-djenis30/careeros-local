from copy import deepcopy
from uuid import uuid4

from backend.career.models import CandidateProfile, CareerFact
from backend.resumes.models import ResumeDraft


def _generate(client, auth_headers, profile):
    response = client.post(
        "/api/v1/resumes/generate",
        json={
            "title": "Editable local resume",
            "template_kind": "ats",
            "career_goal_id": profile["goals"][0]["id"],
        },
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _write_payload(draft):
    return {
        "expected_revision": draft["revision"],
        "title": draft["title"],
        "template_kind": draft["template_kind"],
        "section_config": draft["section_config"],
        "selected_fact_ids": draft["selected_fact_ids"],
        "content_overrides": draft["content_overrides"],
        "photo_asset_id": draft["photo_asset_id"],
        "canvas_document": draft["canvas_document"],
    }


def test_canvas_edit_persists_manual_fields_with_optimistic_revision(
    client, auth_headers, saved_detailed_profile
):
    draft = _generate(client, auth_headers, saved_detailed_profile)
    payload = _write_payload(draft)
    experience = next(
        section
        for section in payload["canvas_document"]["sections"]
        if section["kind"] == "experience"
    )
    experience["blocks"][0]["content"]["title"] = "Principal Platform Engineer"
    experience["blocks"][0]["manual_fields"] = ["title"]
    experience["page_break_before"] = True
    payload["canvas_document"]["style"]["accent_color"] = "#0057B8"

    response = client.put(
        f"/api/v1/resumes/{draft['id']}", json=payload, headers=auth_headers
    )
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["revision"] == 2
    assert saved["canvas_document"]["style"]["accent_color"] == "#0057B8"
    saved_experience = next(
        section
        for section in saved["canvas_document"]["sections"]
        if section["kind"] == "experience"
    )
    assert saved_experience["page_break_before"] is True
    assert saved_experience["blocks"][0]["manual_fields"] == ["title"]

    stale = client.put(
        f"/api/v1/resumes/{draft['id']}", json=payload, headers=auth_headers
    )
    assert stale.status_code == 409


def test_canvas_rejects_unknown_provenance_and_invalid_ats_layout(
    client, auth_headers, saved_detailed_profile
):
    draft = _generate(client, auth_headers, saved_detailed_profile)
    unknown = _write_payload(deepcopy(draft))
    fact_block = next(
        block
        for section in unknown["canvas_document"]["sections"]
        for block in section["blocks"]
        if block["kind"] == "fact"
    )
    unsupported_id = str(uuid4())
    fact_block["fact_ids"] = [unsupported_id]
    unknown["selected_fact_ids"].append(unsupported_id)
    response = client.put(
        f"/api/v1/resumes/{draft['id']}", json=unknown, headers=auth_headers
    )
    assert response.status_code == 422
    assert "missing career facts" in response.text

    multi_column = _write_payload(deepcopy(draft))
    multi_column["canvas_document"]["style"]["columns"] = 2
    response = client.put(
        f"/api/v1/resumes/{draft['id']}", json=multi_column, headers=auth_headers
    )
    assert response.status_code == 422
    assert "single-column" in response.text


def test_publication_rejects_persisted_ungrounded_claim(
    client, auth_headers, db_session, saved_detailed_profile
):
    draft = _generate(client, auth_headers, saved_detailed_profile)
    persisted = db_session.query(ResumeDraft).filter(ResumeDraft.id == draft["id"]).one()
    document = deepcopy(persisted.canvas_document)
    fact_block = next(
        block
        for section in document["sections"]
        for block in section["blocks"]
        if block["kind"] == "fact"
    )
    fact_block["fact_ids"] = []
    persisted.canvas_document = document
    db_session.commit()

    response = client.post(f"/api/v1/resumes/{draft['id']}/publish", headers=auth_headers)
    assert response.status_code == 422
    assert "provenance" in response.text.casefold()


def _add_manual_claim(draft: dict) -> dict:
    payload = _write_payload(deepcopy(draft))
    payload["canvas_document"]["sections"].append(
        {
            "id": "achievement",
            "kind": "achievement",
            "title": "ACHIEVEMENTS",
            "visible": True,
            "page_break_before": False,
            "blocks": [
                {
                    "id": "manual-career-impact",
                    "kind": "fact",
                    "fact_ids": [],
                    "visible": True,
                    "content": {
                        "title": "Built an offline career workflow",
                        "subtitle": "Local-first product delivery",
                        "date_range": "",
                        "description": "Designed the workflow without public AI services.",
                        "bullets": ["Kept all career data on the user's device."],
                    },
                    "manual_fields": ["title", "subtitle", "description", "bullets"],
                }
            ],
        }
    )
    return payload


def test_manual_claim_can_be_saved_as_draft_but_not_published(
    client, auth_headers, saved_detailed_profile
):
    draft = _generate(client, auth_headers, saved_detailed_profile)
    saved = client.put(
        f"/api/v1/resumes/{draft['id']}",
        json=_add_manual_claim(draft),
        headers=auth_headers,
    )

    assert saved.status_code == 200, saved.text
    manual = next(
        block
        for section in saved.json()["canvas_document"]["sections"]
        for block in section["blocks"]
        if block["id"] == "manual-career-impact"
    )
    assert manual["fact_ids"] == []
    blocked = client.post(
        f"/api/v1/resumes/{draft['id']}/publish", headers=auth_headers
    )
    assert blocked.status_code == 422
    assert "provenance" in blocked.text.casefold()


def test_manual_claim_promotion_atomically_revisions_profile_and_draft(
    client, auth_headers, db_session, saved_detailed_profile
):
    draft = _generate(client, auth_headers, saved_detailed_profile)
    saved = client.put(
        f"/api/v1/resumes/{draft['id']}",
        json=_add_manual_claim(draft),
        headers=auth_headers,
    )
    assert saved.status_code == 200, saved.text
    saved_draft = saved.json()

    promoted = client.post(
        f"/api/v1/resumes/{draft['id']}/claims/promote",
        json={
            "expected_revision": saved_draft["revision"],
            "expected_profile_revision": saved_detailed_profile["revision"],
            "block_id": "manual-career-impact",
        },
        headers=auth_headers,
    )

    assert promoted.status_code == 200, promoted.text
    result = promoted.json()
    manual = next(
        block
        for section in result["canvas_document"]["sections"]
        for block in section["blocks"]
        if block["id"] == "manual-career-impact"
    )
    assert len(manual["fact_ids"]) == 1
    fact_id = manual["fact_ids"][0]
    assert fact_id in result["selected_fact_ids"]
    assert result["revision"] == saved_draft["revision"] + 1
    assert result["profile_revision"] == saved_detailed_profile["revision"] + 1

    db_session.expire_all()
    fact = db_session.query(CareerFact).filter(CareerFact.id == fact_id).one()
    profile = db_session.query(CandidateProfile).filter(
        CandidateProfile.id == result["profile_id"]
    ).one()
    assert fact.fact_type == "achievement"
    assert fact.verification_status == "confirmed"
    assert fact.payload["title"] == "Built an offline career workflow"
    assert fact.payload["details"] == ["Kept all career data on the user's device."]
    assert profile.revision == result["profile_revision"]

    stale = client.post(
        f"/api/v1/resumes/{draft['id']}/claims/promote",
        json={
            "expected_revision": saved_draft["revision"],
            "expected_profile_revision": saved_detailed_profile["revision"],
            "block_id": "manual-career-impact",
        },
        headers=auth_headers,
    )
    assert stale.status_code == 409


def test_fact_selection_reconciles_canvas_without_losing_manual_blocks(
    client, auth_headers, saved_detailed_profile
):
    draft = _generate(client, auth_headers, saved_detailed_profile)
    skill_id = next(
        fact["id"]
        for fact in saved_detailed_profile["facts"]
        if fact["fact_type"] == "skill"
    )
    payload = _write_payload(deepcopy(draft))
    payload["selected_fact_ids"].remove(skill_id)
    removed = client.put(
        f"/api/v1/resumes/{draft['id']}", json=payload, headers=auth_headers
    )
    assert removed.status_code == 200, removed.text
    without_skill = removed.json()
    assert all(
        section["kind"] != "skill"
        for section in without_skill["canvas_document"]["sections"]
    )

    restored_payload = _write_payload(without_skill)
    restored_payload["selected_fact_ids"].append(skill_id)
    restored = client.put(
        f"/api/v1/resumes/{draft['id']}", json=restored_payload, headers=auth_headers
    )
    assert restored.status_code == 200, restored.text
    skill_section = next(
        section
        for section in restored.json()["canvas_document"]["sections"]
        if section["kind"] == "skill"
    )
    assert skill_section["blocks"][0]["fact_ids"] == [skill_id]
