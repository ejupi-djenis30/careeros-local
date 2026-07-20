"""Build and verify CareerOS release candidates without network mutations."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from scripts.check_release_versions import ROOT, release_versions, validate_versions
from scripts.release_assets import stage_target_candidate, validate_target_candidate
from scripts.release_contract import assemble_release_bundle, validate_release_bundle


def _version(expected_tag: str | None = None) -> str:
    tag = expected_tag or None
    if tag is None and os.environ.get("GITHUB_REF_TYPE") == "tag":
        tag = os.environ.get("GITHUB_REF_NAME")
    return validate_versions(release_versions(), tag)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    stage = commands.add_parser("stage", help="Normalize one native target candidate")
    stage.add_argument("--target", required=True)
    stage.add_argument("--bundle-root", required=True, type=Path)
    stage.add_argument("--output", required=True, type=Path)
    stage.add_argument("--commit", required=True)
    stage.add_argument("--expected-tag")

    assemble = commands.add_parser("assemble", help="Assemble the exact public bundle")
    assemble.add_argument("--native-root", required=True, type=Path)
    assemble.add_argument("--evidence-root", required=True, type=Path)
    assemble.add_argument("--output", required=True, type=Path)
    assemble.add_argument("--native-checksums", required=True, type=Path)
    assemble.add_argument("--commit", required=True)
    assemble.add_argument("--release-date", required=True)
    assemble.add_argument("--expected-tag")

    verify = commands.add_parser("verify", help="Read-only verification of a public bundle")
    verify.add_argument("--directory", required=True, type=Path)
    verify.add_argument("--commit", required=True)
    verify.add_argument("--release-date", required=True)
    verify.add_argument("--expected-tag")
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    version = _version(arguments.expected_tag)
    license_path = ROOT / "LICENSE"
    if arguments.command == "stage":
        stage_target_candidate(
            bundle_root=arguments.bundle_root,
            output=arguments.output,
            target=arguments.target,
            version=version,
            source_commit=arguments.commit,
        )
        validate_target_candidate(
            arguments.output,
            target=arguments.target,
            version=version,
            source_commit=arguments.commit,
        )
    elif arguments.command == "assemble":
        assemble_release_bundle(
            native_root=arguments.native_root,
            evidence_root=arguments.evidence_root,
            output=arguments.output,
            native_checksums=arguments.native_checksums,
            version=version,
            source_commit=arguments.commit,
            release_date=arguments.release_date,
            license_path=license_path,
        )
    else:
        validate_release_bundle(
            arguments.directory,
            version=version,
            source_commit=arguments.commit,
            release_date=arguments.release_date,
            license_path=license_path,
        )
    print(f"RELEASE_CANDIDATE_OK command={arguments.command} version={version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
