from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from scripts.publish_github_release import Publisher
from scripts.release_github import ApiFailure, GitHubApi, Response
from tests.backend.release.helpers import COMMIT, RELEASE_DATE, VERSION


class FakeReleaseApi:
    def __init__(self) -> None:
        self.release_values: list[dict[str, Any]] = []
        self.asset_values: dict[int, list[dict[str, Any]]] = {}
        self.create_calls = self.upload_calls = self.update_calls = 0
        self.ambiguous_create = self.ambiguous_upload = self.ambiguous_publish = False
        self.latest_id: int | None = None
        self.sleep = lambda _seconds: None

    def releases(self, _repo: str) -> list[dict[str, Any]]:
        return [dict(value) for value in self.release_values]

    def assets(self, _repo: str, release_id: int) -> list[dict[str, Any]]:
        return [dict(value) for value in self.asset_values.get(release_id, [])]

    def release(self, _repo: str, release_id: int) -> dict[str, Any]:
        return dict(next(value for value in self.release_values if value["id"] == release_id))

    def latest(self, _repo: str) -> dict[str, Any]:
        return self.release(_repo, int(self.latest_id))

    def create_release(self, _repo: str, body: dict[str, Any]) -> dict[str, Any]:
        self.create_calls += 1
        release = {
            "id": 101,
            **body,
            "immutable": False,
            "upload_url": "https://uploads.test/releases/101/assets{?name,label}",
        }
        self.release_values.append(release)
        if self.ambiguous_create:
            self.ambiguous_create = False
            raise ApiFailure("lost create response", ambiguous=True)
        return dict(release)

    def upload_asset(self, _url: str, *, name: str, payload: bytes) -> dict[str, Any]:
        self.upload_calls += 1
        asset = {
            "id": 1000 + self.upload_calls,
            "name": name,
            "size": len(payload),
            "digest": f"sha256:{hashlib.sha256(payload).hexdigest()}",
            "state": "uploaded",
        }
        self.asset_values.setdefault(101, []).append(asset)
        if self.ambiguous_upload:
            self.ambiguous_upload = False
            raise ApiFailure("lost upload response", ambiguous=True)
        return dict(asset)

    def update_release(
        self, _repo: str, release_id: int, _body: dict[str, Any]
    ) -> dict[str, Any]:
        self.update_calls += 1
        release = next(value for value in self.release_values if value["id"] == release_id)
        release["draft"] = False
        release["immutable"] = True
        self.latest_id = release_id
        if self.ambiguous_publish:
            self.ambiguous_publish = False
            raise ApiFailure("lost publish response", ambiguous=True)
        return dict(release)


class SequenceRaceApi(FakeReleaseApi):
    def __init__(self) -> None:
        super().__init__()
        self.release_reads = 0

    def releases(self, repo: str) -> list[dict[str, Any]]:
        self.release_reads += 1
        if self.release_reads == 2:
            self.release_values.append(
                {
                    "id": 202,
                    "tag_name": "v1.2.0",
                    "draft": False,
                    "immutable": True,
                }
            )
            self.latest_id = 202
        return super().releases(repo)


def _publisher(tmp_path: Path, api: FakeReleaseApi) -> Publisher:
    directory = tmp_path / "release"
    directory.mkdir()
    (directory / "release-manifest.json").write_text("{}\n", encoding="utf-8")
    (directory / "SHA256SUMS").write_text("inventory\n", encoding="utf-8")
    (directory / "CareerOS-Local_1.1.1_windows-x64-setup.exe").write_bytes(b"installer")
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n## [1.1.1] - 2026-07-20\n\n### Fixed\n\n- Exact releases.\n",
        encoding="utf-8",
    )
    return Publisher(
        api=api,
        repo="owner/repo",
        directory=directory,
        version=VERSION,
        source_commit=COMMIT,
        release_date=RELEASE_DATE,
        changelog=changelog,
    )


def _seed_exact_published(publisher: Publisher, api: FakeReleaseApi) -> None:
    release = {
        "id": 101,
        "tag_name": publisher.tag,
        "target_commitish": COMMIT,
        "name": publisher.name,
        "body": publisher.body,
        "draft": False,
        "prerelease": False,
        "immutable": True,
        "upload_url": "unused",
    }
    api.release_values.append(release)
    api.asset_values[101] = [
        {
            "id": index,
            "name": name,
            "size": record["size"],
            "digest": f"sha256:{record['sha256']}",
            "state": "uploaded",
        }
        for index, (name, record) in enumerate(publisher.expected.items(), start=1)
    ]
    api.latest_id = 101


def test_publisher_recovers_ambiguous_create_upload_and_publish(tmp_path: Path) -> None:
    api = FakeReleaseApi()
    publisher = _publisher(tmp_path, api)
    api.ambiguous_create = api.ambiguous_upload = api.ambiguous_publish = True

    release = publisher.publish()

    assert release["immutable"] is True
    assert api.create_calls == 1
    assert api.upload_calls == len(publisher.expected)
    assert api.update_calls == 1


def test_exact_immutable_latest_release_is_a_write_free_noop(tmp_path: Path) -> None:
    api = FakeReleaseApi()
    publisher = _publisher(tmp_path, api)
    _seed_exact_published(publisher, api)

    assert publisher.publish()["id"] == 101
    assert (api.create_calls, api.upload_calls, api.update_calls) == (0, 0, 0)


def test_partial_exact_draft_resumes_only_missing_uploads(tmp_path: Path) -> None:
    api = FakeReleaseApi()
    publisher = _publisher(tmp_path, api)
    _seed_exact_published(publisher, api)
    api.release_values[0]["draft"] = True
    api.release_values[0]["immutable"] = False
    api.asset_values[101] = api.asset_values[101][:1]
    already_present = len(api.asset_values[101])

    publisher.publish()

    assert api.create_calls == 0
    assert api.upload_calls == len(publisher.expected) - already_present
    assert api.update_calls == 1


def test_mismatched_existing_asset_is_never_clobbered(tmp_path: Path) -> None:
    api = FakeReleaseApi()
    publisher = _publisher(tmp_path, api)
    _seed_exact_published(publisher, api)
    api.release_values[0]["draft"] = True
    api.release_values[0]["immutable"] = False
    api.asset_values[101][0]["digest"] = "sha256:" + "0" * 64

    with pytest.raises(RuntimeError, match="differs from candidate"):
        publisher.publish()
    assert api.upload_calls == 0


def test_duplicate_release_and_stale_canonical_draft_fail_closed(tmp_path: Path) -> None:
    api = FakeReleaseApi()
    publisher = _publisher(tmp_path, api)
    exact = {
        "id": 101,
        "tag_name": publisher.tag,
        "name": publisher.name,
        "body": publisher.body,
        "draft": True,
    }
    api.release_values = [exact, {**exact, "id": 102}]
    with pytest.raises(RuntimeError, match="Duplicate"):
        publisher.publish()

    api.release_values = [
        {
            **exact,
            "id": 103,
            "tag_name": "v1.0.9",
            "name": "CareerOS Local v1.0.9",
            "body": "legacy draft without a contract marker",
        }
    ]
    with pytest.raises(RuntimeError, match="stale or foreign"):
        publisher.publish()


def test_foreign_or_extra_remote_assets_fail_closed(tmp_path: Path) -> None:
    api = FakeReleaseApi()
    publisher = _publisher(tmp_path, api)
    _seed_exact_published(publisher, api)
    api.asset_values[101].append(
        {
            "id": 9999,
            "name": "foreign.bin",
            "size": 1,
            "digest": "sha256:00",
            "state": "uploaded",
        }
    )

    with pytest.raises(RuntimeError, match="unexpected assets"):
        publisher.publish()


def test_mutable_published_or_nonlatest_release_fails_closed(tmp_path: Path) -> None:
    api = FakeReleaseApi()
    publisher = _publisher(tmp_path, api)
    _seed_exact_published(publisher, api)
    api.release_values[0]["immutable"] = False
    with pytest.raises(RuntimeError, match="immutable"):
        publisher.publish()

    api.release_values[0]["immutable"] = True
    api.release_values.append({"id": 999, "draft": False})
    api.latest_id = 999
    with pytest.raises(RuntimeError, match="not latest"):
        publisher.publish()


def test_candidate_must_advance_every_published_version(tmp_path: Path) -> None:
    api = FakeReleaseApi()
    publisher = _publisher(tmp_path, api)
    api.release_values.append({"id": 99, "draft": False, "tag_name": "v2.0.0"})

    with pytest.raises(RuntimeError, match="does not advance"):
        publisher.publish()


def test_sequence_is_rediscovered_immediately_before_promotion(tmp_path: Path) -> None:
    api = SequenceRaceApi()
    publisher = _publisher(tmp_path, api)

    with pytest.raises(RuntimeError, match="does not advance"):
        publisher.publish()

    candidate = next(release for release in api.release_values if release["id"] == 101)
    assert candidate["draft"] is True
    assert candidate["immutable"] is False
    assert api.latest_id == 202
    assert api.update_calls == 0


def test_duplicate_candidate_on_a_later_release_page_fails_closed(tmp_path: Path) -> None:
    publisher = _publisher(tmp_path, FakeReleaseApi())
    exact = {
        "id": 101,
        "tag_name": publisher.tag,
        "name": publisher.name,
        "body": publisher.body,
        "draft": True,
    }
    responses = iter(
        [
            Response(
                200,
                {
                    "link": (
                        '<https://api.github.com/repos/owner/repo/releases?per_page=100&page=2>; '
                        'rel="next"'
                    )
                },
                [exact],
            ),
            Response(200, {}, [{**exact, "id": 102}]),
        ]
    )
    api = GitHubApi.__new__(GitHubApi)
    api.sleep = lambda _seconds: None
    api._request = lambda *_args, **_kwargs: next(responses)  # type: ignore[method-assign]
    publisher.api = api

    with pytest.raises(RuntimeError, match="Duplicate"):
        publisher.publish()
