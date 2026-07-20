"""Publish an exact CareerOS release contract with crash-safe reconciliation."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Protocol

from scripts.check_release_versions import ROOT, release_versions, validate_versions
from scripts.release_assets import STABLE_VERSION, sha256_file
from scripts.release_contract import (
    GLOBAL_CHECKSUMS,
    RELEASE_MANIFEST,
    inventory_directory,
    validate_release_bundle,
)
from scripts.release_github import ApiFailure, GitHubApi, verify_source_policy

CONTRACT_PREFIX = "<!-- careeros-release-contract:"
RELEASE_NAME_PREFIX = "CareerOS Local v"


class ReleaseApi(Protocol):
    sleep: Any

    def releases(self, repo: str) -> list[dict[str, Any]]: ...
    def assets(self, repo: str, release_id: int) -> list[dict[str, Any]]: ...
    def release(self, repo: str, release_id: int) -> dict[str, Any]: ...
    def latest(self, repo: str) -> dict[str, Any]: ...
    def create_release(self, repo: str, body: dict[str, Any]) -> dict[str, Any]: ...
    def update_release(
        self, repo: str, release_id: int, body: dict[str, Any]
    ) -> dict[str, Any]: ...
    def upload_asset(self, upload_url: str, *, name: str, payload: bytes) -> dict[str, Any]: ...


def _object(value: Any, message: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError(message)
    return value


def _release_notes(changelog: Path, *, version: str, release_date: str) -> str:
    text = changelog.read_text(encoding="utf-8")
    marker = f"## [{version}] - {release_date}"
    start = text.find(marker)
    if start < 0:
        raise RuntimeError(f"CHANGELOG.md has no curated {marker} section")
    next_section = text.find("\n## [", start + len(marker))
    section = text[start + len(marker) : next_section if next_section >= 0 else None].strip()
    if not section:
        raise RuntimeError("Curated release notes are empty")
    return section


def release_body(
    directory: Path, *, version: str, source_commit: str, release_date: str, changelog: Path
) -> str:
    contract = {
        "project": "CareerOS Local",
        "schema": 1,
        "version": version,
        "tag": f"v{version}",
        "sourceCommit": source_commit,
        "releaseManifestSha256": sha256_file(directory / RELEASE_MANIFEST),
        "sha256sumsSha256": sha256_file(directory / GLOBAL_CHECKSUMS),
    }
    marker = CONTRACT_PREFIX + json.dumps(contract, separators=(",", ":"), sort_keys=True) + " -->"
    notes = _release_notes(
        changelog, version=version, release_date=release_date
    )
    verification = (
        "Packages are unsigned community builds. Verify `SHA256SUMS` and GitHub attestations "
        "before installation."
    )
    return f"{notes}\n\n{verification}\n\n{marker}"


def _version_key(value: str) -> tuple[int, int, int]:
    if not STABLE_VERSION.fullmatch(value):
        raise RuntimeError(f"Published CareerOS release is not stable SemVer: {value}")
    return tuple(int(part) for part in value.split("."))  # type: ignore[return-value]


def _release_id(release: dict[str, Any]) -> int:
    value = release.get("id")
    if not isinstance(value, int):
        raise RuntimeError("GitHub release has no numeric ID")
    return value


def _asset_map(assets: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    folded: set[str] = set()
    identifiers: set[int] = set()
    for asset in assets:
        name = asset.get("name")
        identifier = asset.get("id")
        if (
            not isinstance(name, str)
            or name.casefold() in folded
            or not isinstance(identifier, int)
            or identifier in identifiers
        ):
            raise RuntimeError(
                "Release contains invalid, duplicate, unnamed, or case-colliding assets"
            )
        folded.add(name.casefold())
        identifiers.add(identifier)
        result[name] = asset
    return result


def _assert_asset(asset: dict[str, Any], expected: dict[str, Any]) -> None:
    digest = f"sha256:{expected['sha256']}"
    if (
        asset.get("name") != expected["name"]
        or asset.get("size") != expected["size"]
        or asset.get("digest") != digest
        or asset.get("state") != "uploaded"
    ):
        raise RuntimeError(f"Remote release asset differs from candidate: {expected['name']}")


class Publisher:
    def __init__(
        self,
        *,
        api: ReleaseApi,
        repo: str,
        directory: Path,
        version: str,
        source_commit: str,
        release_date: str,
        changelog: Path,
    ):
        self.api = api
        self.repo = repo
        self.directory = directory
        self.version = version
        self.tag = f"v{version}"
        self.source_commit = source_commit
        self.name = f"{RELEASE_NAME_PREFIX}{version}"
        self.body = release_body(
            directory,
            version=version,
            source_commit=source_commit,
            release_date=release_date,
            changelog=changelog,
        )
        self.expected = {
            str(record["name"]): record for record in inventory_directory(directory)
        }

    def _discover(self) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        releases = self.api.releases(self.repo)
        tagged = [release for release in releases if release.get("tag_name") == self.tag]
        if len(tagged) > 1:
            raise RuntimeError("Duplicate releases use the candidate tag")
        for release in releases:
            body = release.get("body")
            canonical = isinstance(body, str) and CONTRACT_PREFIX in body
            name = release.get("name")
            named = isinstance(name, str) and name.startswith(RELEASE_NAME_PREFIX)
            if release.get("draft") is True and (canonical or named):
                if release not in tagged:
                    raise RuntimeError("A stale or foreign CareerOS draft blocks publication")
        return (tagged[0] if tagged else None), releases

    def _assert_identity(self, release: dict[str, Any], *, draft: bool, immutable: bool) -> None:
        expected = {
            "tag_name": self.tag,
            "target_commitish": self.source_commit,
            "name": self.name,
            "body": self.body,
            "draft": draft,
            "prerelease": False,
            "immutable": immutable,
        }
        for key, value in expected.items():
            if release.get(key) != value:
                raise RuntimeError(f"GitHub release has unexpected {key}: {release.get(key)!r}")

    def _assert_sequence(self, releases: list[dict[str, Any]]) -> None:
        current = _version_key(self.version)
        for release in releases:
            tag = release.get("tag_name")
            if release.get("draft") is True or not isinstance(tag, str) or tag == self.tag:
                continue
            match = re.fullmatch(r"v(.+)", tag)
            if match and _version_key(match.group(1)) >= current:
                raise RuntimeError("Candidate version does not advance all published CareerOS releases")

    def _assert_assets(self, release: dict[str, Any], *, allow_missing: bool) -> set[str]:
        actual = _asset_map(self.api.assets(self.repo, _release_id(release)))
        unexpected = set(actual) - set(self.expected)
        if unexpected:
            raise RuntimeError(f"Release contains unexpected assets: {sorted(unexpected)}")
        for name, asset in actual.items():
            _assert_asset(asset, self.expected[name])
        missing = set(self.expected) - set(actual)
        if missing and not allow_missing:
            raise RuntimeError(f"Release is missing assets: {sorted(missing)}")
        return missing

    def _create_or_recover(self) -> dict[str, Any]:
        payload = {
            "tag_name": self.tag,
            "target_commitish": self.source_commit,
            "name": self.name,
            "body": self.body,
            "draft": True,
            "prerelease": False,
        }
        try:
            release = self.api.create_release(self.repo, payload)
        except ApiFailure as error:
            if not error.ambiguous:
                raise
            recovered, _ = self._discover()
            if recovered is None:
                raise RuntimeError("Ambiguous draft creation did not reconcile safely") from error
            release = recovered
        self._assert_identity(release, draft=True, immutable=False)
        return release

    def _upload_or_recover(self, release: dict[str, Any], name: str) -> None:
        upload_url = release.get("upload_url")
        if not isinstance(upload_url, str):
            raise RuntimeError("Draft release has no upload URL")
        try:
            self.api.upload_asset(upload_url, name=name, payload=(self.directory / name).read_bytes())
        except ApiFailure as error:
            if not error.ambiguous:
                raise
            try:
                self._wait_for_uploaded_asset(release, name)
            except RuntimeError as recovery_error:
                raise RuntimeError(
                    f"Ambiguous upload did not reconcile safely: {name}"
                ) from recovery_error
            return
        self._wait_for_uploaded_asset(release, name)

    def _wait_for_uploaded_asset(self, release: dict[str, Any], name: str) -> None:
        expected = self.expected[name]
        release_id = _release_id(release)
        for attempt in range(12):
            actual = _asset_map(self.api.assets(self.repo, release_id))
            asset = actual.get(name)
            if asset is not None:
                digest = asset.get("digest")
                state = asset.get("state")
                if digest == f"sha256:{expected['sha256']}" and state == "uploaded":
                    _assert_asset(asset, expected)
                    return
                if (
                    asset.get("size") != expected["size"]
                    or digest not in {None, f"sha256:{expected['sha256']}"}
                    or state not in {"new", "uploaded"}
                ):
                    _assert_asset(asset, expected)
            if attempt < 11:
                self.api.sleep(2)
        raise RuntimeError(f"Uploaded asset did not become digest-verifiable: {name}")

    def _publish_or_recover(self, release: dict[str, Any]) -> dict[str, Any]:
        release_id = _release_id(release)
        try:
            current = self.api.update_release(
                self.repo, release_id, {"draft": False, "make_latest": "true"}
            )
        except ApiFailure as error:
            if not error.ambiguous:
                raise
            current = self.api.release(self.repo, release_id)
        for attempt in range(12):
            if current.get("draft") is False and current.get("immutable") is True:
                return current
            if attempt == 11:
                break
            self.api.sleep(5)
            current = self.api.release(self.repo, release_id)
        raise RuntimeError("Published release did not become immutable")

    def _require_latest(self, release: dict[str, Any]) -> None:
        release_id = _release_id(release)
        for attempt in range(12):
            if _release_id(self.api.latest(self.repo)) == release_id:
                return
            if attempt < 11:
                self.api.sleep(2)
        raise RuntimeError("Exact immutable release is not latest")

    def publish(self) -> dict[str, Any]:
        release, releases = self._discover()
        self._assert_sequence(releases)
        if release is not None and release.get("draft") is False:
            self._assert_identity(release, draft=False, immutable=True)
            self._assert_assets(release, allow_missing=False)
            self._require_latest(release)
            return release
        release = release or self._create_or_recover()
        self._assert_identity(release, draft=True, immutable=False)
        for name in sorted(self._assert_assets(release, allow_missing=True), key=str.casefold):
            self._upload_or_recover(release, name)
        self._assert_assets(release, allow_missing=False)
        published = self._publish_or_recover(release)
        self._assert_identity(published, draft=False, immutable=True)
        self._assert_assets(published, allow_missing=False)
        self._require_latest(published)
        return published


def _require_publish_context(tag: str, source_commit: str) -> None:
    expected = {
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_REF_TYPE": "tag",
        "GITHUB_REF_NAME": tag,
        "GITHUB_SHA": source_commit,
    }
    for name, value in expected.items():
        if os.environ.get(name) != value:
            raise RuntimeError(f"Publisher requires {name}={value}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--release-date", required=True)
    arguments = parser.parse_args()
    version = validate_versions(release_versions(), os.environ.get("GITHUB_REF_NAME"))
    tag = f"v{version}"
    _require_publish_context(tag, arguments.commit)
    validate_release_bundle(
        arguments.directory,
        version=version,
        source_commit=arguments.commit,
        release_date=arguments.release_date,
        license_path=ROOT / "LICENSE",
    )
    api = GitHubApi(token=os.environ.get("GITHUB_TOKEN", ""))
    verify_source_policy(api, repo=arguments.repo, tag=tag, source_commit=arguments.commit)
    publisher = Publisher(
        api=api,
        repo=arguments.repo,
        directory=arguments.directory,
        version=version,
        source_commit=arguments.commit,
        release_date=arguments.release_date,
        changelog=ROOT / "CHANGELOG.md",
    )
    release = publisher.publish()
    verify_source_policy(api, repo=arguments.repo, tag=tag, source_commit=arguments.commit)
    print(f"RELEASE_PUBLISHED id={_release_id(release)} tag={tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
