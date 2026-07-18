from __future__ import annotations

from collections.abc import Collection, Mapping
from copy import deepcopy
from typing import Any

import pytest

from scripts import seed_demo


class FakeApi:
    def __init__(self, responses: list[seed_demo.ApiResult]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def request_json(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, Any] | None = None,
        form: Mapping[str, str] | None = None,
        token: str | None = None,
        allowed_statuses: Collection[int] = (200,),
    ) -> seed_demo.ApiResult:
        self.calls.append(
            {
                "method": method,
                "path": path,
                "payload": payload,
                "form": form,
                "token": token,
                "allowed_statuses": tuple(allowed_statuses),
            }
        )
        if not self.responses:
            raise AssertionError(f"Unexpected request: {method} {path}")
        response = self.responses.pop(0)
        assert response.status in allowed_statuses
        return response


class ApiTestAdapter:
    def __init__(self, client) -> None:
        self.client = client

    def request_json(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, Any] | None = None,
        form: Mapping[str, str] | None = None,
        token: str | None = None,
        allowed_statuses: Collection[int] = (200,),
    ) -> seed_demo.ApiResult:
        headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
        response = self.client.request(
            method,
            f"/api/v1{path}",
            json=dict(payload) if payload is not None else None,
            data=dict(form) if form is not None else None,
            headers=headers,
        )
        assert response.status_code in allowed_statuses, response.text
        value = response.json() if response.content else None
        return seed_demo.ApiResult(response.status_code, value)


def _ready_profile() -> dict[str, Any]:
    profile = deepcopy(seed_demo.PROFILE_PAYLOAD)
    profile.update({"id": "profile-id", "revision": 1})
    return profile


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("http://127.0.0.1:8000/", "http://127.0.0.1:8000"),
        ("https://localhost:8443", "https://localhost:8443"),
        ("http://[::1]:8000", "http://[::1]:8000"),
        ("http://127.42.0.9", "http://127.42.0.9"),
    ],
)
def test_normalize_base_url_accepts_only_canonical_loopback_origins(value, expected):
    assert seed_demo.normalize_base_url(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "https://example.com",
        "http://0.0.0.0:8000",
        "http://localhost.example:8000",
        "ftp://127.0.0.1:8000",
        "http://user:secret@127.0.0.1:8000",
        "http://127.0.0.1:8000/api/v1",
        "http://127.0.0.1:8000?target=external",
        "",
    ],
)
def test_normalize_base_url_rejects_non_loopback_or_ambiguous_targets(value):
    with pytest.raises(seed_demo.SeedError):
        seed_demo.normalize_base_url(value)


def test_first_seed_creates_verified_profile_ats_resume_and_application():
    api = FakeApi(
        [
            seed_demo.ApiResult(200, {"access_token": "secret-token"}),
            seed_demo.ApiResult(404),
            seed_demo.ApiResult(200, _ready_profile()),
            seed_demo.ApiResult(200, []),
            seed_demo.ApiResult(
                201,
                {"title": seed_demo.DEMO_RESUME_TITLE, "template_kind": "ats"},
            ),
            seed_demo.ApiResult(200, []),
            seed_demo.ApiResult(
                201,
                {
                    "job_snapshot": {
                        "title": seed_demo.DEMO_JOB_TITLE,
                        "company": seed_demo.DEMO_JOB_COMPANY,
                    }
                },
            ),
        ]
    )

    summary = seed_demo.seed_demo(api, "ada_demo", "AdaDemo2026!")

    assert summary == seed_demo.SeedSummary("created", "created", "created", "created")
    profile_write = next(call for call in api.calls if call["method"] == "PUT")
    assert {
        fact["verification_status"] for fact in profile_write["payload"]["facts"]
    } == {"confirmed"}
    assert any(call["path"] == "/resumes/generate" for call in api.calls)
    assert any(call["path"] == "/applications" and call["method"] == "POST" for call in api.calls)
    assert "secret-token" not in summary.render()


def test_repeat_seed_reuses_owned_demo_records_without_product_writes():
    api = FakeApi(
        [
            seed_demo.ApiResult(400),
            seed_demo.ApiResult(200, {"access_token": "different-secret-token"}),
            seed_demo.ApiResult(200, _ready_profile()),
            seed_demo.ApiResult(
                200,
                [{"title": seed_demo.DEMO_RESUME_TITLE, "template_kind": "ats"}],
            ),
            seed_demo.ApiResult(
                200,
                [
                    {
                        "title": seed_demo.DEMO_JOB_TITLE,
                        "company": seed_demo.DEMO_JOB_COMPANY,
                    }
                ],
            ),
        ]
    )

    summary = seed_demo.seed_demo(api, "ada_demo", "AdaDemo2026!")

    assert summary == seed_demo.SeedSummary("reused", "reused", "reused", "reused")
    product_writes = [
        call
        for call in api.calls
        if call["method"] in {"POST", "PUT"} and not call["path"].startswith("/auth/")
    ]
    assert product_writes == []


def test_seed_payloads_match_the_real_api_and_second_run_is_idempotent(client):
    api = ApiTestAdapter(client)

    first = seed_demo.seed_demo(api, "ada_contract", "AdaContract2026!")
    second = seed_demo.seed_demo(api, "ada_contract", "AdaContract2026!")

    assert first == seed_demo.SeedSummary("created", "created", "created", "created")
    assert second == seed_demo.SeedSummary("reused", "reused", "reused", "reused")


def test_existing_unrelated_profile_is_not_overwritten():
    api = FakeApi(
        [
            seed_demo.ApiResult(400),
            seed_demo.ApiResult(200, {"access_token": "secret-token"}),
            seed_demo.ApiResult(200, {"display_name": "Existing User", "facts": []}),
        ]
    )

    with pytest.raises(seed_demo.SeedError, match="use another username"):
        seed_demo.seed_demo(api, "existing_user", "Existing2026!")

    assert not any(call["method"] == "PUT" for call in api.calls)


def test_cli_prints_one_secret_free_summary(monkeypatch, capsys):
    observed: dict[str, str] = {}

    def fake_seed(api, username: str, password: str):
        assert isinstance(api, seed_demo.ApiClient)
        observed.update(username=username, password=password)
        return seed_demo.SeedSummary("created", "created", "created", "created")

    monkeypatch.setattr(seed_demo, "seed_demo", fake_seed)
    result = seed_demo.main(
        [
            "--base-url",
            "http://127.0.0.1:9876",
            "--username",
            "ada_judge",
            "--password",
            "DoNotPrint2026!",
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert observed == {"username": "ada_judge", "password": "DoNotPrint2026!"}
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert "DoNotPrint2026!" not in captured.out
    assert "Bearer" not in captured.out
