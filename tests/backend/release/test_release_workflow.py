from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "desktop-release.yml"
TAURI_CONFIG = ROOT / "frontend" / "src-tauri" / "tauri.conf.json"
WINDOWS_SMOKE = ROOT / "scripts" / "smoke_windows_installer.ps1"


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
        "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6.3.0",
        "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8.0.1",
        "actions/attest@f7c74d28b9d84cb8768d0b8ca14a4bac6ef463e6 # v4.2.0",
        "tauri-apps/tauri-action@1deb371b0cd8bd54025b384f1cd735e725c4060f # v1.0.0",
    ):
        assert exact in text
    assert "-latest" not in text
    assert "toolchain: stable" not in text


def test_native_build_forwards_locked_and_consumes_metadata_portably() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    cargo_metadata = (
        "cargo metadata --manifest-path frontend/src-tauri/Cargo.toml "
        "--locked --format-version 1 |"
    )
    assert text.count(cargo_metadata) == 2
    assert text.count('python -c "import json, sys; json.load(sys.stdin)"') == 2
    assert (
        "args: --target ${{ matrix.target }} --bundles ${{ matrix.bundles }} "
        "-- --locked"
    ) in text
    assert (
        "args: --target ${{ matrix.target }} --bundles ${{ matrix.bundles }} "
        "--locked"
    ) not in text


def test_tag_publications_share_one_group_without_cancelling_the_running_tag() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert (
        "group: desktop-${{ github.workflow }}-${{ "
        "github.ref_type == 'tag' && 'tag-publication' || github.ref }}" in text
    )
    assert "cancel-in-progress: ${{ github.ref_type != 'tag' }}" in text
    assert "desktop-${{ github.workflow }}-${{ github.ref }}" not in text


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
    assert text.index("python -m scripts.smoke_native_bundle") < text.index(
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


def test_canonical_project_license_is_bundled_and_checked_in_every_native_path() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    config = json.loads(TAURI_CONFIG.read_text(encoding="utf-8"))
    windows_smoke = WINDOWS_SMOKE.read_text(encoding="utf-8")

    assert config["bundle"]["resources"]["../../LICENSE"] == "LICENSE"
    assert "LICENSE text eol=lf" in (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "-IncludeNsisInstall" in workflow
    assert "python -m scripts.smoke_native_bundle --target" in workflow
    assert "python scripts/smoke_native_bundle.py" not in workflow
    assert "Assert-PackagedLicense ($MsiApp.Directory.FullName)" in windows_smoke
    assert "Assert-PackagedLicense ($NsisApp.Directory.FullName)" in windows_smoke
