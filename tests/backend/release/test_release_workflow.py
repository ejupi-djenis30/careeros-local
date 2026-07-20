from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "desktop-release.yml"


def test_required_check_name_and_versioned_toolchains_are_stable() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "name: Release supply-chain evidence" in text
    for exact in (
        'PYTHON_VERSION: "3.12.10"',
        'NODE_VERSION: "24.18.0"',
        'RUST_VERSION: "1.96.0"',
        "runner: windows-2025",
        "runner: windows-11-arm",
        "runner: macos-15-intel",
        "runner: macos-15",
        "runner: ubuntu-24.04",
        "runner: ubuntu-24.04-arm",
        'GH_CLI_VERSION: "2.94.0"',
    ):
        assert exact in text
    assert "-latest" not in text
    assert "toolchain: stable" not in text


def test_required_check_is_emitted_for_every_pull_request() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    pull_request_trigger = text.index("  pull_request:")
    push_trigger = text.index("  push:", pull_request_trigger)
    trigger_config = text[pull_request_trigger:push_trigger]

    assert trigger_config.strip() == "pull_request:"
    assert "paths:" not in trigger_config
    assert "paths-ignore:" not in trigger_config


def test_only_tag_push_job_can_attest_or_publish() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    publisher = text.index("  attest-publish:")
    read_only = text[:publisher]
    tag_only = text[publisher:]

    assert "github.event_name == 'push'" in tag_only
    assert "github.ref_type == 'tag'" in tag_only
    assert "id-token: write" not in read_only
    assert "attestations: write" not in read_only
    assert "contents: write" not in read_only
    assert "actions/attest@" not in read_only
    assert "publish_github_release" not in read_only
    assert "id-token: write" in tag_only
    assert "contents: write" in tag_only


def test_release_contract_is_collision_safe_and_never_clobbers() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "scripts.release_candidate stage" in text
    assert "scripts.release_candidate assemble" in text
    assert "scripts.release_candidate verify" in text
    assert text.index("scripts/smoke_native_bundle.py") < text.index(
        "scripts.release_candidate stage"
    )
    assert "merge-multiple: true" not in text
    assert "--clobber" not in text
    assert "gh release create" not in text
    assert "gh release upload" not in text
    assert "subject-checksums: release-assets/SHA256SUMS" in text
    assert text.count("sbom-path:") == 3
    assert "https://cyclonedx.org/bom" in text
    assert "scripts.verify_sbom_attestations" in text
    assert "--deny-self-hosted-runners" in text
