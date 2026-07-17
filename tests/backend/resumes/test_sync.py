from copy import deepcopy


def _generate(client, headers, profile):
    response = client.post(
        "/api/v1/resumes/generate",
        json={
            "title": "Leadership resume",
            "template_kind": "ats",
            "career_goal_id": profile["goals"][0]["id"],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _write(draft):
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


def _experience(canvas):
    return next(section for section in canvas["sections"] if section["kind"] == "experience")


def test_duplicate_is_an_independent_exact_canvas_copy(
    client, auth_headers, saved_detailed_profile
):
    original = _generate(client, auth_headers, saved_detailed_profile)
    response = client.post(
        f"/api/v1/resumes/{original['id']}/duplicate",
        json={"title": "Tailored copy"},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    duplicate = response.json()
    assert duplicate["id"] != original["id"]
    assert duplicate["revision"] == 1
    assert duplicate["title"] == "Tailored copy"
    assert duplicate["canvas_document"] == original["canvas_document"]
    assert duplicate["generation_context"] == original["generation_context"]

    payload = _write(duplicate)
    _experience(payload["canvas_document"])["blocks"][0]["content"]["title"] = "Copy only"
    _experience(payload["canvas_document"])["blocks"][0]["manual_fields"] = ["title"]
    assert client.put(
        f"/api/v1/resumes/{duplicate['id']}", json=payload, headers=auth_headers
    ).status_code == 200
    reloaded_original = client.get(
        f"/api/v1/resumes/{original['id']}", headers=auth_headers
    ).json()
    assert _experience(reloaded_original["canvas_document"])["blocks"][0]["content"][
        "title"
    ] != "Copy only"


def test_sync_preview_selective_apply_reset_and_stale_revision(
    client, auth_headers, saved_detailed_profile, detailed_profile_payload
):
    draft = _generate(client, auth_headers, saved_detailed_profile)
    manual = _write(draft)
    experience = _experience(manual["canvas_document"])
    experience["blocks"][0]["content"]["title"] = "Hand-tailored Principal Engineer"
    experience["blocks"][0]["manual_fields"] = ["title"]
    edited_response = client.put(
        f"/api/v1/resumes/{draft['id']}", json=manual, headers=auth_headers
    )
    assert edited_response.status_code == 200, edited_response.text
    edited = edited_response.json()

    profile_update = deepcopy(detailed_profile_payload)
    profile_update["expected_revision"] = saved_detailed_profile["revision"]
    profile_update["summary"] = "Leads privacy-first engineering organizations at scale."
    for index, fact in enumerate(profile_update["facts"]):
        fact["id"] = saved_detailed_profile["facts"][index]["id"]
    profile_update["goals"][0]["id"] = saved_detailed_profile["goals"][0]["id"]
    profile_update["facts"].append(
        {
            "fact_type": "skill",
            "position": 3,
            "verification_status": "confirmed",
            "payload": {
                "name": "Go",
                "category": "Engineering",
                "level": "advanced",
                "years": 4,
            },
        }
    )
    updated_profile_response = client.put(
        "/api/v1/career-profile", json=profile_update, headers=auth_headers
    )
    assert updated_profile_response.status_code == 200, updated_profile_response.text
    updated_profile = updated_profile_response.json()

    stale = client.post(
        f"/api/v1/resumes/{draft['id']}/sync",
        json={"expected_revision": 1, "mode": "preview", "sections": []},
        headers=auth_headers,
    )
    assert stale.status_code == 409

    preview = client.post(
        f"/api/v1/resumes/{draft['id']}/sync",
        json={"expected_revision": edited["revision"], "mode": "preview", "sections": []},
        headers=auth_headers,
    )
    assert preview.status_code == 200, preview.text
    preview_data = preview.json()
    assert preview_data["applied"] is False
    by_kind = {section["kind"]: section for section in preview_data["sections"]}
    assert by_kind["skill"]["added_fact_ids"]
    assert by_kind["summary"]["changed_fact_ids"]
    assert any(item.endswith(":title") for item in preview_data["preserved_manual_fields"])

    applied = client.post(
        f"/api/v1/resumes/{draft['id']}/sync",
        json={
            "expected_revision": edited["revision"],
            "mode": "apply",
            "sections": ["summary", "skill"],
        },
        headers=auth_headers,
    )
    assert applied.status_code == 200, applied.text
    synchronized = applied.json()["draft"]
    assert synchronized["profile_revision"] == updated_profile["revision"]
    assert _experience(synchronized["canvas_document"])["blocks"][0]["content"][
        "title"
    ] == "Hand-tailored Principal Engineer"
    skill = next(
        section
        for section in synchronized["canvas_document"]["sections"]
        if section["kind"] == "skill"
    )
    assert {block["content"]["title"] for block in skill["blocks"]} >= {"Python", "Go"}

    reset = client.post(
        f"/api/v1/resumes/{draft['id']}/sync",
        json={
            "expected_revision": synchronized["revision"],
            "mode": "reset",
            "sections": [],
        },
        headers=auth_headers,
    )
    assert reset.status_code == 200, reset.text
    reset_draft = reset.json()["draft"]
    reset_experience = _experience(reset_draft["canvas_document"])["blocks"][0]
    assert reset_experience["content"]["title"] == "Principal Engineer"
    assert reset_experience["manual_fields"] == []
