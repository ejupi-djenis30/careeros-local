from pathlib import Path
from tempfile import TemporaryDirectory


def _profile_payload(expected_revision=0):
    return {
        "expected_revision": expected_revision,
        "display_name": "Ada Lovelace",
        "headline": "Computing pioneer",
        "summary": "Builds rigorous analytical systems.",
        "email": "ada@example.test",
        "phone": "+41 79 000 00 00",
        "location": {"city": "Zurich", "country": "CH"},
        "preferences": {"remote": True, "workload_min": 80, "workload_max": 100},
        "facts": [
            {
                "fact_type": "experience",
                "position": 0,
                "verification_status": "confirmed",
                "payload": {
                    "role": "Analytical Engineer",
                    "organization": "Independent",
                    "start_date": "1842-01-01",
                    "end_date": "1843-12-31",
                    "achievements": ["Published the first algorithm for the engine."],
                },
            },
            {
                "fact_type": "language",
                "position": 1,
                "verification_status": "confirmed",
                "payload": {"language": "English", "level": "native"},
            },
        ],
        "goals": [
            {
                "name": "Local systems",
                "is_primary": True,
                "payload": {"target_roles": ["Staff Engineer"], "work_modes": ["remote"]},
            }
        ],
    }


def test_career_profile_round_trip_and_optimistic_revision(client, auth_headers):
    created = client.put("/api/v1/career-profile", json=_profile_payload(), headers=auth_headers)
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["revision"] == 1
    assert len(body["facts"]) == 2
    assert all(item["id"] for item in body["facts"])

    loaded = client.get("/api/v1/career-profile", headers=auth_headers)
    assert loaded.status_code == 200
    assert loaded.json()["email"] == "ada@example.test"

    stale = client.put("/api/v1/career-profile", json=_profile_payload(0), headers=auth_headers)
    assert stale.status_code == 409

    updated_payload = _profile_payload(1)
    updated_payload["headline"] = "Local-first career systems pioneer"
    updated_payload["facts"][0]["id"] = body["facts"][0]["id"]
    updated_payload["facts"][1]["id"] = body["facts"][1]["id"]
    updated = client.put("/api/v1/career-profile", json=updated_payload, headers=auth_headers)
    assert updated.status_code == 200, updated.text
    assert updated.json()["revision"] == 2
    assert updated.json()["facts"][0]["id"] == body["facts"][0]["id"]


def test_career_profile_summary_omits_private_fields_and_fact_bodies(client, auth_headers):
    response = client.put("/api/v1/career-profile", json=_profile_payload(), headers=auth_headers)
    assert response.status_code == 200

    summary = client.get("/api/v1/career-profile/summary", headers=auth_headers)
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["display_name"] == "Ada Lovelace"
    assert payload["fact_counts"] == {"experience": 1, "language": 1}
    assert "email" not in payload
    assert "facts" not in payload


def test_career_profile_requires_authentication(client):
    assert client.get("/api/v1/career-profile").status_code == 401


def test_source_document_import_is_local_hashed_and_idempotent(client, auth_headers, monkeypatch):
    profile = client.put("/api/v1/career-profile", json=_profile_payload(), headers=auth_headers)
    assert profile.status_code == 200, profile.text
    with TemporaryDirectory() as directory:
        data_dir = Path(directory)
        monkeypatch.setattr("backend.career.sources.settings.DATA_DIR", str(data_dir))
        content = b"Evidence-backed local career history."

        first = client.post(
            "/api/v1/career-profile/sources",
            headers=auth_headers,
            files={"file": ("career.txt", content, "text/plain")},
        )
        assert first.status_code == 201, first.text
        payload = first.json()
        assert payload["original_name"] == "career.txt"
        assert payload["extracted_characters"] == len(content.decode())
        assert payload["text_preview"] == content.decode()
        assert len(payload["candidates"]) == 1
        candidate = payload["candidates"][0]
        assert candidate["fact_type"] == "achievement"
        assert candidate["source_locator"] == "paragraph:1"
        stored = data_dir / "assets" / payload["sha256"][:2] / payload["sha256"]
        assert stored.read_bytes() == content

        duplicate = client.post(
            "/api/v1/career-profile/sources",
            headers=auth_headers,
            files={"file": ("renamed.txt", content, "text/plain")},
        )
        assert duplicate.status_code == 201
        assert duplicate.json()["id"] == payload["id"]
        assert duplicate.json()["candidates"] == payload["candidates"]

        updated = _profile_payload(1)
        updated["facts"].append(
            {
                "fact_type": candidate["fact_type"],
                "position": 2,
                "payload": candidate["payload"],
                "source_document_id": payload["id"],
                "source_locator": candidate["source_locator"],
                "confidence": candidate["confidence"],
                "verification_status": "imported",
            }
        )
        accepted = client.put(
            "/api/v1/career-profile", json=updated, headers=auth_headers
        )
        assert accepted.status_code == 200, accepted.text
        imported = next(
            item
            for item in accepted.json()["facts"]
            if item["verification_status"] == "imported"
        )
        assert imported["source_document_id"] == payload["id"]
        assert imported["source_locator"] == "paragraph:1"
        assert imported["confidence"] == candidate["confidence"]


def test_source_document_skill_candidates_are_deterministic(client, auth_headers, monkeypatch):
    profile = client.put("/api/v1/career-profile", json=_profile_payload(), headers=auth_headers)
    assert profile.status_code == 200
    with TemporaryDirectory() as directory:
        monkeypatch.setattr("backend.career.sources.settings.DATA_DIR", directory)
        response = client.post(
            "/api/v1/career-profile/sources",
            headers=auth_headers,
            files={"file": ("skills.txt", b"Competenze: Python, FastAPI; SQL", "text/plain")},
        )

    assert response.status_code == 201, response.text
    candidates = response.json()["candidates"]
    assert [item["payload"]["name"] for item in candidates] == ["Python", "FastAPI", "SQL"]
    assert all(item["fact_type"] == "skill" for item in candidates)
    assert len({item["candidate_id"] for item in candidates}) == 3


def test_source_document_import_rejects_unsupported_media_type(client, auth_headers):
    profile = client.put("/api/v1/career-profile", json=_profile_payload(), headers=auth_headers)
    assert profile.status_code == 200

    response = client.post(
        "/api/v1/career-profile/sources",
        headers=auth_headers,
        files={"file": ("career.csv", b"not,a,supported,source", "text/csv")},
    )

    assert response.status_code == 415
    assert "Supported source formats" in response.json()["detail"]
