"""Small, testable GitHub Releases client and source-policy verifier."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Iterator

from scripts.release_assets import validate_source_commit

API = "https://api.github.com"
OIDC_ISSUER = "https://token.actions.githubusercontent.com"
ALLOWED_API_HOSTS = {"api.github.com", "uploads.github.com"}


class ApiFailure(RuntimeError):
    """An API failure, annotated when the server may have applied a write."""

    def __init__(self, message: str, *, status: int | None = None, ambiguous: bool = False):
        super().__init__(message)
        self.status = status
        self.ambiguous = ambiguous


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict[str, str]
    payload: Any


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args: Any, **_kwargs: Any) -> None:
        return None


def _api_url(value: str) -> str:
    absolute = f"{API}{value}" if value.startswith("/") else value
    parsed = urllib.parse.urlsplit(absolute)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_API_HOSTS
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise RuntimeError(f"Refusing an untrusted GitHub API URL: {value}")
    return absolute


class GitHubApi:
    def __init__(self, *, token: str, sleep: Callable[[float], None] = time.sleep):
        if not token:
            raise RuntimeError("GITHUB_TOKEN is required")
        self._token = token
        self.sleep = sleep

    def _request(
        self,
        method: str,
        url: str,
        *,
        body: bytes | None = None,
        content_type: str = "application/json",
        expected: tuple[int, ...] = (200,),
    ) -> Response:
        absolute = _api_url(url)
        request = urllib.request.Request(absolute, data=body, method=method)
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("Authorization", f"Bearer {self._token}")
        request.add_header("X-GitHub-Api-Version", "2022-11-28")
        if body is not None:
            request.add_header("Content-Type", content_type)
        try:
            opener = urllib.request.build_opener(_NoRedirect())
            with opener.open(request, timeout=60) as result:
                payload_bytes = result.read()
                status = result.status
                headers = {key.lower(): value for key, value in result.headers.items()}
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")[:1000]
            raise ApiFailure(
                f"GitHub API {method} {url} failed ({error.code}): {details}",
                status=error.code,
                ambiguous=error.code >= 500 and method != "GET",
            ) from error
        except (TimeoutError, urllib.error.URLError, ConnectionError) as error:
            raise ApiFailure(
                f"GitHub API {method} {url} did not return a definitive response",
                ambiguous=method != "GET",
            ) from error
        if status not in expected:
            raise ApiFailure(
                f"GitHub API {method} {url} returned unexpected status {status}",
                status=status,
                ambiguous=status >= 500 and method != "GET",
            )
        if not payload_bytes:
            payload: Any = None
        elif headers.get("content-type", "").startswith("application/json"):
            payload = json.loads(payload_bytes)
        else:
            payload = payload_bytes
        return Response(status, headers, payload)

    def json(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> Any:
        encoded = json.dumps(body).encode("utf-8") if body is not None else None
        return self._request(method, path, body=encoded, expected=expected).payload

    def pages(self, path: str, *, maximum: int = 100) -> Iterator[list[dict[str, Any]]]:
        next_url: str | None = path
        count = 0
        while next_url is not None:
            count += 1
            if count > maximum:
                raise RuntimeError("GitHub pagination exceeded the fail-closed page limit")
            response = self._request("GET", next_url)
            if not isinstance(response.payload, list):
                raise RuntimeError("GitHub paginated response is not a list")
            yield response.payload
            next_url = _next_link(response.headers.get("link"))

    def releases(self, repo: str) -> list[dict[str, Any]]:
        path = f"/repos/{repo}/releases?per_page=100&page=1"
        return [release for page in self.pages(path) for release in page]

    def assets(self, repo: str, release_id: int) -> list[dict[str, Any]]:
        path = f"/repos/{repo}/releases/{release_id}/assets?per_page=100&page=1"
        return [asset for page in self.pages(path) for asset in page]

    def release(self, repo: str, release_id: int) -> dict[str, Any]:
        return _object(self.json("GET", f"/repos/{repo}/releases/{release_id}"))

    def latest(self, repo: str) -> dict[str, Any]:
        return _object(self.json("GET", f"/repos/{repo}/releases/latest"))

    def create_release(self, repo: str, body: dict[str, Any]) -> dict[str, Any]:
        return _object(
            self.json("POST", f"/repos/{repo}/releases", body=body, expected=(201,))
        )

    def update_release(self, repo: str, release_id: int, body: dict[str, Any]) -> dict[str, Any]:
        return _object(
            self.json("PATCH", f"/repos/{repo}/releases/{release_id}", body=body)
        )

    def upload_asset(self, upload_url: str, *, name: str, payload: bytes) -> dict[str, Any]:
        base = upload_url.split("{", 1)[0]
        url = f"{base}?name={urllib.parse.quote(name, safe='')}"
        return _object(
            self._request(
                "POST",
                url,
                body=payload,
                content_type="application/octet-stream",
                expected=(201,),
            ).payload
        )


def _next_link(value: str | None) -> str | None:
    if not value:
        return None
    for item in value.split(","):
        parts = [part.strip() for part in item.split(";")]
        if len(parts) == 2 and parts[1] == 'rel="next"':
            return parts[0].removeprefix("<").removesuffix(">")
    return None


def _object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError("GitHub API response is not an object")
    return value


def _repo_state(api: GitHubApi, repo: str) -> tuple[str, str]:
    repository = _object(api.json("GET", f"/repos/{repo}"))
    branch = repository.get("default_branch")
    if not isinstance(branch, str) or not branch:
        raise RuntimeError("Repository has no usable default branch")
    encoded = urllib.parse.quote(branch, safe="")
    commit = _object(api.json("GET", f"/repos/{repo}/commits/{encoded}"))
    sha = commit.get("sha")
    if not isinstance(sha, str):
        raise RuntimeError("Default branch head has no commit SHA")
    return branch, validate_source_commit(sha)


def _resolve_annotated_tag(api: GitHubApi, repo: str, tag: str) -> str:
    encoded = urllib.parse.quote(tag, safe="")
    reference = _object(api.json("GET", f"/repos/{repo}/git/ref/tags/{encoded}"))
    target = _object(reference.get("object"))
    if target.get("type") != "tag":
        raise RuntimeError("Release tags must be annotated, not lightweight")
    seen: set[str] = set()
    for _ in range(8):
        sha = target.get("sha")
        if not isinstance(sha, str) or sha in seen:
            raise RuntimeError("Annotated tag chain is invalid or cyclic")
        seen.add(sha)
        tag_object = _object(api.json("GET", f"/repos/{repo}/git/tags/{sha}"))
        verification = _object(tag_object.get("verification"))
        if verification.get("verified") is not True:
            raise RuntimeError("Every annotated tag object must be GitHub-verified")
        target = _object(tag_object.get("object"))
        if target.get("type") == "commit":
            commit = target.get("sha")
            if not isinstance(commit, str):
                raise RuntimeError("Annotated tag does not resolve to a commit")
            return validate_source_commit(commit)
        if target.get("type") != "tag":
            raise RuntimeError("Annotated tag chain resolves to an unsupported object")
    raise RuntimeError("Annotated tag chain is unreasonably deep")


def _require_contained(api: GitHubApi, *, repo: str, source_commit: str, head: str) -> None:
    comparison = _object(api.json("GET", f"/repos/{repo}/compare/{source_commit}...{head}"))
    merge_base = _object(comparison.get("merge_base_commit"))
    if comparison.get("status") not in {"ahead", "identical"} or merge_base.get(
        "sha"
    ) != source_commit:
        raise RuntimeError("Release source is not contained in the current default branch")


def verify_source_policy(api: GitHubApi, *, repo: str, tag: str, source_commit: str) -> str:
    source_commit = validate_source_commit(source_commit)
    branch_before, head_before = _repo_state(api, repo)
    resolved = _resolve_annotated_tag(api, repo, tag)
    if resolved != source_commit:
        raise RuntimeError("Verified tag does not resolve to the release candidate commit")
    _require_contained(api, repo=repo, source_commit=source_commit, head=head_before)
    branch_after, head_after = _repo_state(api, repo)
    if branch_after != branch_before:
        raise RuntimeError("Default branch identity changed during source verification")
    if head_after != head_before:
        _require_contained(api, repo=repo, source_commit=source_commit, head=head_after)
    if _resolve_annotated_tag(api, repo, tag) != source_commit:
        raise RuntimeError("Release tag moved while source policy was evaluated")
    return branch_before
