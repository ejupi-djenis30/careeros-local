from __future__ import annotations

from typing import Any

import pytest

from scripts.release_github import GitHubApi, Response, _api_url, verify_source_policy
from tests.backend.release.helpers import COMMIT


class SourceApi:
    def __init__(
        self,
        *,
        annotated: bool = True,
        verified: bool = True,
        moving: bool = False,
        renamed: bool = False,
        contained: bool = True,
    ):
        self.annotated = annotated
        self.verified = verified
        self.moving = moving
        self.renamed = renamed
        self.contained = contained
        self.branch_reads = 0
        self.repo_reads = 0

    def json(self, _method: str, path: str) -> Any:
        if path == "/repos/owner/repo":
            self.repo_reads += 1
            branch = "trunk" if self.renamed and self.repo_reads > 1 else "main"
            return {"default_branch": branch}
        if path in {"/repos/owner/repo/commits/main", "/repos/owner/repo/commits/trunk"}:
            self.branch_reads += 1
            return {"sha": ("b" if self.moving and self.branch_reads > 1 else "a") * 40}
        if path == "/repos/owner/repo/git/ref/tags/v1.1.2":
            return {"object": {"type": "tag" if self.annotated else "commit", "sha": "c" * 40}}
        if path == "/repos/owner/repo/git/tags/" + "c" * 40:
            return {
                "verification": {"verified": self.verified},
                "object": {"type": "commit", "sha": COMMIT},
            }
        if path == f"/repos/owner/repo/compare/{COMMIT}...{'a' * 40}":
            if not self.contained:
                return {"status": "diverged", "merge_base_commit": {"sha": "d" * 40}}
            return {"status": "ahead", "merge_base_commit": {"sha": COMMIT}}
        if path == f"/repos/owner/repo/compare/{COMMIT}...{'b' * 40}":
            return {"status": "ahead", "merge_base_commit": {"sha": COMMIT}}
        raise AssertionError(path)


def test_source_policy_requires_verified_annotated_tag_on_stable_default_branch() -> None:
    assert (
        verify_source_policy(
            SourceApi(), repo="owner/repo", tag="v1.1.2", source_commit=COMMIT
        )
        == "main"
    )

    with pytest.raises(RuntimeError, match="annotated"):
        verify_source_policy(
            SourceApi(annotated=False), repo="owner/repo", tag="v1.1.2", source_commit=COMMIT
        )
    with pytest.raises(RuntimeError, match="GitHub-verified"):
        verify_source_policy(
            SourceApi(verified=False), repo="owner/repo", tag="v1.1.2", source_commit=COMMIT
        )
    assert verify_source_policy(
        SourceApi(moving=True), repo="owner/repo", tag="v1.1.2", source_commit=COMMIT
    ) == "main"
    with pytest.raises(RuntimeError, match="identity changed"):
        verify_source_policy(
            SourceApi(renamed=True), repo="owner/repo", tag="v1.1.2", source_commit=COMMIT
        )


def test_verified_annotated_tag_outside_default_branch_fails_closed() -> None:
    with pytest.raises(RuntimeError, match="not contained"):
        verify_source_policy(
            SourceApi(contained=False),
            repo="owner/repo",
            tag="v1.1.2",
            source_commit=COMMIT,
        )


def test_pagination_follows_next_links_and_enforces_bound() -> None:
    api = GitHubApi.__new__(GitHubApi)
    responses = iter(
        [
            Response(200, {"link": '<https://api.github.test/page/2>; rel="next"'}, [{"id": 1}]),
            Response(200, {}, [{"id": 2}]),
        ]
    )
    api._request = lambda *_args, **_kwargs: next(responses)  # type: ignore[method-assign]

    assert list(api.pages("/first")) == [[{"id": 1}], [{"id": 2}]]

    endless = Response(200, {"link": '<https://api.github.test/next>; rel="next"'}, [])
    api._request = lambda *_args, **_kwargs: endless  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="page limit"):
        list(api.pages("/first", maximum=2))


@pytest.mark.parametrize(
    "value",
    [
        "http://api.github.com/repos/owner/repo",
        "https://evil.example/steal",
        "https://token@api.github.com/repos/owner/repo",
        "relative-without-leading-slash",
    ],
)
def test_api_urls_cannot_exfiltrate_the_token(value: str) -> None:
    with pytest.raises(RuntimeError, match="untrusted"):
        _api_url(value)
