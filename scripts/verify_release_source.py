"""Read-only verification of the release tag and default-branch source policy."""

from __future__ import annotations

import argparse
import os

from scripts.release_github import GitHubApi, verify_source_policy


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    arguments = parser.parse_args()
    api = GitHubApi(token=os.environ.get("GITHUB_TOKEN", ""))
    branch = verify_source_policy(
        api,
        repo=arguments.repo,
        tag=arguments.tag,
        source_commit=arguments.commit,
    )
    print(f"RELEASE_SOURCE_OK tag={arguments.tag} commit={arguments.commit} branch={branch}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
