def _profile_payload():
    return {
        "expected_revision": 0,
        "display_name": "Mira Vale",
        "headline": "Lead Systems Architect",
        "summary": "Specialist in reliable distributed systems and local computation.",
        "email": "mira.vale@example.ch",
        "phone": "+41 44 123 45 67",
        "location": {"city": "Zurich", "country": "CH"},
        "website": "https://miravale.ch",
        "preferences": {},
        "facts": [
            {
                "fact_type": "experience",
                "position": 0,
                "verification_status": "confirmed",
                "payload": {
                    "role": "Systems Architect",
                    "organization": "Alpine Cloud Systems",
                    "start_date": "2021-03-01",
                    "current": True,
                    "description": "Architected low-latency streaming pipelines.",
                    "achievements": ["Reduced latency by 45%."],
                },
            },
        ],
        "goals": [],
    }


def _create_profile(client, auth_headers):
    response = client.put("/api/v1/career-profile", json=_profile_payload(), headers=auth_headers)
    assert response.status_code == 200, response.text
    profile = response.json()
    return profile, profile["facts"][0]


def test_template_switch_preserves_facts_overrides_and_manual_blocks(client, auth_headers):
    profile, fact = _create_profile(client, auth_headers)

    # 1. Create ATS draft
    create_payload = {
        "title": "Dual-Language Architect",
        "template_kind": "ats",
        "template_id": "software-en",
        "template_version": 1,
        "locale": "en",
        "selected_fact_ids": [fact["id"]],
        "content_overrides": {
            fact["id"]: {
                "title": "Custom Overridden Role Title",
                "description": "Custom overridden description text.",
            }
        },
        "section_config": {"order": ["experience"], "include_summary": True},
    }
    created = client.post("/api/v1/resumes", json=create_payload, headers=auth_headers)
    assert created.status_code == 201, created.text
    draft = created.json()
    assert draft["template_id"] == "software-en"
    assert draft["template_kind"] == "ats"
    assert draft["locale"] == "en"

    # 2. Switch to Swiss Software DE
    switch_payload = {
        "expected_revision": draft["revision"],
        "title": draft["title"],
        "template_kind": "photo",
        "template_id": "swiss-software-de",
        "template_version": 1,
        "locale": "de",
        "selected_fact_ids": draft["selected_fact_ids"],
        "content_overrides": draft["content_overrides"],
        "section_config": draft["section_config"],
        "canvas_document": draft["canvas_document"],
    }
    switched = client.put(
        f"/api/v1/resumes/{draft['id']}", json=switch_payload, headers=auth_headers
    )
    assert switched.status_code == 200, switched.text
    switched_draft = switched.json()

    # Verify template metadata updated
    assert switched_draft["template_id"] == "swiss-software-de"
    assert switched_draft["template_kind"] == "photo"
    assert switched_draft["locale"] == "de"

    # Verify selected facts and content overrides preserved intact
    assert switched_draft["selected_fact_ids"] == [fact["id"]]
    assert (
        switched_draft["content_overrides"][fact["id"]]["title"] == "Custom Overridden Role Title"
    )
    assert "Custom" in switched_draft["content_overrides"][fact["id"]]["description"]


def test_duplicate_and_restore_preserves_template_metadata(
    client, auth_headers, monkeypatch, tmp_path
):
    monkeypatch.setattr("backend.storage.atomic.settings.DATA_DIR", str(tmp_path))
    profile, fact = _create_profile(client, auth_headers)

    # 1. Create draft with Swiss Infrastructure DE preset
    create_payload = {
        "title": "Infrastructure Spec",
        "template_id": "swiss-infrastructure-de",
        "template_version": 1,
        "locale": "de",
        "selected_fact_ids": [fact["id"]],
        "content_overrides": {},
        "section_config": {"order": ["experience"], "include_summary": True},
    }
    created = client.post("/api/v1/resumes", json=create_payload, headers=auth_headers)
    assert created.status_code == 201, created.text
    draft = created.json()
    assert draft["template_id"] == "swiss-infrastructure-de"
    assert draft["locale"] == "de"

    # 2. Duplicate draft
    dup_resp = client.post(
        f"/api/v1/resumes/{draft['id']}/duplicate",
        json={"title": "Infrastructure Spec Copy"},
        headers=auth_headers,
    )
    assert dup_resp.status_code == 201, dup_resp.text
    duplicated = dup_resp.json()
    assert duplicated["template_id"] == "swiss-infrastructure-de"
    assert duplicated["template_version"] == 1
    assert duplicated["locale"] == "de"
    assert duplicated["template_kind"] == "photo"

    # 3. Publish original draft to create immutable version
    pub_resp = client.post(
        f"/api/v1/resumes/{draft['id']}/publish",
        json={"name": "v1-infra"},
        headers=auth_headers,
    )
    assert pub_resp.status_code == 201, pub_resp.text
    version = pub_resp.json()
    assert version["template_id"] == "swiss-infrastructure-de"
    assert version["template_version"] == 1
    assert version["locale"] == "de"

    # 4. Modify original draft to software-en
    update_payload = {
        "expected_revision": draft["revision"],
        "title": "Changed to ATS",
        "template_id": "software-en",
        "template_version": 1,
        "locale": "en",
        "selected_fact_ids": draft["selected_fact_ids"],
        "content_overrides": {},
        "section_config": draft["section_config"],
    }
    updated = client.put(
        f"/api/v1/resumes/{draft['id']}", json=update_payload, headers=auth_headers
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["template_id"] == "software-en"

    # 5. Restore version onto draft
    restore_resp = client.post(
        f"/api/v1/resumes/{draft['id']}/versions/{version['id']}/restore",
        json={"expected_revision": updated.json()["revision"]},
        headers=auth_headers,
    )
    assert restore_resp.status_code == 200, restore_resp.text
    restored = restore_resp.json()
    assert restored["template_id"] == "swiss-infrastructure-de"
    assert restored["template_version"] == 1
    assert restored["locale"] == "de"
    assert restored["template_kind"] == "photo"
