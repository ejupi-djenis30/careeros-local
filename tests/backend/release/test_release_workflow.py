from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from scripts import verify_sidecar_build
from scripts.check_release_versions import (
    changelog_release_date,
    release_versions,
    validate_versions,
)

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "desktop-release.yml"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
TAURI_CONFIG = ROOT / "frontend" / "src-tauri" / "tauri.conf.json"
TAURI_CAPABILITY = ROOT / "frontend" / "src-tauri" / "capabilities" / "main.json"
NSIS_HOOKS = ROOT / "frontend" / "src-tauri" / "windows" / "nsis-hooks.nsh"
WINDOWS_SMOKE = ROOT / "scripts" / "smoke_windows_installer.ps1"
NATIVE_SMOKE = ROOT / "scripts" / "smoke_native_bundle.py"
NATIVE_TARGETS = ROOT / ".github" / "native-targets.json"


@pytest.mark.parametrize(
    ("workflow_path", "retention_days"),
    ((WORKFLOW, 14), (CI_WORKFLOW, 7)),
)
def test_uploaded_artifacts_have_bounded_retention(
    workflow_path: Path,
    retention_days: int,
) -> None:
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    uploads = [
        step
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if str(step.get("uses", "")).startswith("actions/upload-artifact@")
    ]

    assert uploads
    assert all(step.get("with", {}).get("retention-days") == retention_days for step in uploads)


def test_native_opener_is_scoped_to_https_and_mailto() -> None:
    capability = json.loads(TAURI_CAPABILITY.read_text(encoding="utf-8"))
    opener_permissions = [
        permission
        for permission in capability["permissions"]
        if isinstance(permission, dict)
        and str(permission.get("identifier", "")).startswith("opener:")
    ]

    assert opener_permissions == [
        {
            "identifier": "opener:allow-open-url",
            "allow": [{"url": "https://*"}, {"url": "mailto:*"}],
        }
    ]
    assert "opener:allow-default-urls" not in capability["permissions"]


def test_native_window_is_local_only_without_shell_or_devtools_access() -> None:
    capability = json.loads(TAURI_CAPABILITY.read_text(encoding="utf-8"))
    config = json.loads(TAURI_CONFIG.read_text(encoding="utf-8"))
    permissions = capability["permissions"]

    assert capability["local"] is True
    assert capability["windows"] == ["main"]
    assert {
        "shell:deny-execute",
        "shell:deny-kill",
        "shell:deny-open",
        "shell:deny-spawn",
        "shell:deny-stdin-write",
    } <= set(permission for permission in permissions if isinstance(permission, str))
    assert not any(
        permission.startswith("shell:allow-")
        for permission in permissions
        if isinstance(permission, str)
    )
    assert "core:webview:deny-internal-toggle-devtools" in permissions
    assert config["app"]["windows"][0]["devtools"] is False


def test_nsis_uninstall_preserves_coexisting_msi_registration() -> None:
    config = json.loads(TAURI_CONFIG.read_text(encoding="utf-8"))
    hooks = NSIS_HOOKS.read_text(encoding="utf-8")
    windows_smoke = WINDOWS_SMOKE.read_text(encoding="utf-8")

    assert config["bundle"]["windows"]["nsis"]["installerHooks"] == ("windows/nsis-hooks.nsh")
    assert config["bundle"]["windows"]["nsis"]["installMode"] == "currentUser"
    assert "!macro NSIS_HOOK_PREUNINSTALL" in hooks
    assert "!macro NSIS_HOOK_POSTUNINSTALL" in hooks
    assert "${If} $UpdateMode <> 1" in hooks
    assert "Windows Installer ownership detected" in hooks
    assert "Uninstall that MSI package first" in hooks
    assert "Abort" in hooks
    assert 'DeleteRegValue HKCU "Software\\careeros\\CareerOS Local" ""' in hooks
    assert 'DeleteRegValue HKCU "Software\\careeros\\CareerOS Local" "Installer Language"' in hooks
    assert 'DeleteRegKey /ifempty HKCU "Software\\careeros\\CareerOS Local"' in hooks
    assert 'DeleteRegKey /ifempty HKCU "Software\\careeros"' in hooks
    assert 'DeleteRegKey HKCU "Software\\careeros\\CareerOS Local"' not in hooks
    pre_uninstall = hooks.index("!macro NSIS_HOOK_PREUNINSTALL")
    post_uninstall = hooks.index("!macro NSIS_HOOK_POSTUNINSTALL")
    assert pre_uninstall < post_uninstall
    assert "UpdateMode" not in hooks[pre_uninstall:post_uninstall]
    read_msi_registration = hooks.index(
        'ReadRegStr $CareerOSMsiInstallDir HKCU "Software\\careeros\\CareerOS Local" "InstallDir"'
    )
    abort_uninstall = hooks.index("Abort")
    assert hooks.index("SetRegView 64") < read_msi_registration < abort_uninstall
    assert hooks.index("SetRegView 32", read_msi_registration) < abort_uninstall
    assert hooks.count("${IfNot} ${Errors}") == 1
    assert hooks.count("SetErrorLevel 1") == 1
    assert "WriteReg" not in hooks
    for private_path_token in ("$APPDATA", "$LOCALAPPDATA", "${BUNDLEID}", "$INSTDIR", "RmDir"):
        assert private_path_token not in hooks
    assert "function Assert-NsisLocationMetadataRemoved" in windows_smoke
    assert "NSIS uninstall left installer location metadata" in windows_smoke
    assert "function Assert-NsisRegistryCoexistenceOrdering" in windows_smoke
    assert "Assert-NsisRegistryCoexistenceOrdering $NsisTemplate" in windows_smoke
    assert "function Add-SmokeMsiRegistration" in windows_smoke
    assert "function Assert-SmokeMsiRegistration" in windows_smoke
    assert "NSIS uninstall did not reject a coexisting MSI registration" in windows_smoke
    assert "Blocked NSIS uninstall removed MSI-owned payload" in windows_smoke
    assert 'ArgumentList @("/S", "_?=$InstallRoot")' in windows_smoke
    assert 'ArgumentList @("/S", "/UPDATE", "_?=$InstallRoot")' in windows_smoke
    assert "NSIS update uninstall did not reject" in windows_smoke
    assert "Blocked NSIS update uninstall removed MSI-owned payload" in windows_smoke
    assert "function Wait-NsisInstallationRemoved" in windows_smoke
    assert "RegistryView]::Registry32" in windows_smoke
    assert "RegistryView]::Registry64" in windows_smoke
    assert "function Open-InstallerRegistryKey" in windows_smoke
    assert windows_smoke.count("Remove-SmokeMsiRegistration") >= 2
    for msi_value in (
        "InstallDir",
        "Desktop Shortcut",
        "Uninstaller Shortcut",
        "Start Menu Shortcut",
    ):
        assert f'"{msi_value}"' in windows_smoke
    pre_hook = windows_smoke.index("!insertmacro NSIS_HOOK_PREUNINSTALL")
    shared_key_delete = windows_smoke.index('DeleteRegKey SHCTX "${MANUPRODUCTKEY}"')
    post_hook = windows_smoke.index("!insertmacro NSIS_HOOK_POSTUNINSTALL")
    assert pre_hook < shared_key_delete < post_hook


def test_release_workflow_date_matches_the_current_changelog_release() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    match = re.search(
        r'^  RELEASE_DATE: "(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2})"$',
        text,
        re.MULTILINE,
    )

    assert match is not None
    version = validate_versions(release_versions(ROOT))
    assert match.group("date") == changelog_release_date(version, ROOT)


def test_required_check_name_and_versioned_toolchains_are_stable() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    targets = NATIVE_TARGETS.read_text(encoding="utf-8")

    assert "name: Release supply-chain evidence" in text
    for exact in (
        'PYTHON_VERSION: "3.12.13"',
        'NODE_VERSION: "24.18.0"',
        'RUST_VERSION: "1.96.0"',
        'GH_CLI_VERSION: "2.94.0"',
        "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6.3.0",
        "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8.0.1",
        "actions/attest@f7c74d28b9d84cb8768d0b8ca14a4bac6ef463e6 # v4.2.0",
        "tauri-apps/tauri-action@1deb371b0cd8bd54025b384f1cd735e725c4060f # v1.0.0",
    ):
        assert exact in text
    for runner in (
        "windows-2025",
        "windows-11-arm",
        "macos-15-intel",
        "macos-15",
        "ubuntu-24.04",
        "ubuntu-24.04-arm",
    ):
        assert f'"runner": "{runner}"' in targets
    assert "-latest" not in text
    assert "toolchain: stable" not in text


def test_runtime_version_files_and_frontend_engine_are_exactly_bounded() -> None:
    package = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    package_lock = json.loads((ROOT / "frontend" / "package-lock.json").read_text(encoding="utf-8"))

    assert (ROOT / ".python-version").read_text(encoding="utf-8").strip() == "3.12.13"
    assert (ROOT / ".nvmrc").read_text(encoding="utf-8").strip() == "24.18.0"
    assert package["engines"]["node"] == ">=24.18.0 <25"
    assert package_lock["packages"][""]["engines"]["node"] == ">=24.18.0 <25"
    assert (ROOT / "frontend" / ".npmrc").read_text(encoding="utf-8").strip() == (
        "engine-strict=true"
    )
    scripts = package["scripts"]
    preflight = "npm run preflight:node"
    assert scripts["preflight:node"] == "node ../scripts/check_node_version.mjs"

    # Every user-facing npm entry point is Node/Vite/Playwright/Tauri-backed except
    # the explicit Python-only sidecar preparation command. Deriving this set from
    # the manifest makes a newly added command fail the contract until it receives
    # the same exact runtime preflight.
    preflight_hooks = {name for name, command in scripts.items() if command == preflight}
    node_entrypoints = set(scripts) - preflight_hooks - {"preflight:node", "desktop:prepare"}
    assert node_entrypoints == {
        "brand:icons",
        "build",
        "demo:install",
        "demo:record",
        "dev",
        "icons:build",
        "lint",
        "preview",
        "tauri",
        "tauri:build",
        "tauri:dev",
        "test",
        "test:agent-access-quality",
        "test:agenda-responsive",
        "test:coverage",
        "test:e2e",
        "test:icons",
        "test:licenses",
        "test:login-quality",
        "test:pages",
        "test:shell-responsive",
        "test:watch",
    }
    for entrypoint in node_entrypoints:
        assert scripts[f"pre{entrypoint}"] == preflight
    assert "Node.js 24.18.0 (`>=24.18.0 <25`; pinned in `.nvmrc`)" in (
        ROOT / "README.md"
    ).read_text(encoding="utf-8")
    assert "Node.js 24.18.0 (`>=24.18.0 <25`; use the repository `.nvmrc`)" in (
        ROOT / "docs" / "development.md"
    ).read_text(encoding="utf-8")


def test_native_build_forwards_locked_and_consumes_metadata_portably() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert text.count("cargo metadata --manifest-path frontend/src-tauri/Cargo.toml") == 2
    assert text.count("--locked --format-version 1") == 2
    assert text.count('python -c "import json, sys; json.load(sys.stdin)"') == 2
    assert (
        "args: --target ${{ matrix.target }} --bundles ${{ matrix.bundles }} -- --locked"
    ) in text
    assert (
        "args: --target ${{ matrix.target }} --bundles ${{ matrix.bundles }} --locked"
    ) not in text
    assert "python -m scripts.verify_sidecar_build" in text
    assert "python scripts/verify_sidecar_build.py" not in text


def test_source_built_cryptography_uses_verified_static_openssl() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert 'OPENSSL_SOURCE_VERSION: "3.6.3"' in text
    assert "Configure OpenSSL for source-built macOS Intel wheels" in text
    assert "matrix.target == 'x86_64-apple-darwin'" in text
    assert 'open_ssl_root="$(brew --prefix openssl@3)"' in text
    assert 'installed_version="$(brew list --versions openssl@3' in text
    assert '"$open_ssl_root/include/openssl/ssl.h"' in text
    assert '"$open_ssl_root/lib/libcrypto.a"' in text
    assert '"$open_ssl_root/lib/libssl.a"' in text
    assert 'echo "OPENSSL_DIR=$open_ssl_root"' in text

    assert "Configure OpenSSL for source-built Windows ARM64 wheels" in text
    assert "matrix.target == 'aarch64-pc-windows-msvc'" in text
    assert 'Join-Path $env:ProgramFiles "OpenSSL"' in text
    assert ('$openSslStaticLibraryRoot = Join-Path $openSslRoot "lib\\VC\\arm64\\MD"') in text
    assert ('"libcrypto.lib" = Join-Path $openSslStaticLibraryRoot "libcrypto_static.lib"') in text
    assert ('"libssl.lib" = Join-Path $openSslStaticLibraryRoot "libssl_static.lib"') in text
    assert "Copy-Item -LiteralPath $library.Value" in text
    assert '"OPENSSL_INCLUDE_DIR=$openSslInclude"' in text
    assert '"OPENSSL_LIB_DIR=$staticLibraryDirectory"' in text
    assert '"OPENSSL_DIR=$openSslRoot"' not in text
    assert text.count("OPENSSL_STATIC=1") == 2
    assert text.count("PIP_NO_CACHE_DIR=1") == 2


@pytest.mark.parametrize(
    ("dependency", "expected"),
    (
        ("@rpath/libssl.3.dylib", True),
        ("C:\\OpenSSL\\bin\\libcrypto-3-arm64.dll", True),
        ("LIBEAY32.dll", True),
        ("ssleay32.dll", True),
        ("/usr/lib/libSystem.B.dylib", False),
        ("KERNEL32.dll", False),
    ),
)
def test_dynamic_openssl_dependency_detection(dependency: str, expected: bool) -> None:
    assert verify_sidecar_build._is_dynamic_openssl_dependency(dependency) is expected


def test_source_build_linkage_gate_rejects_dynamic_openssl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extension = tmp_path / "cryptography" / "hazmat" / "bindings" / "_rust.abi3.so"
    extension.parent.mkdir(parents=True)
    extension.write_bytes(b"native-extension")
    monkeypatch.setattr(
        verify_sidecar_build,
        "_macos_dependencies",
        lambda _extension: (
            "/usr/lib/libSystem.B.dylib",
            "/usr/local/opt/openssl@3/lib/libssl.3.dylib",
        ),
    )

    with pytest.raises(RuntimeError, match="must link OpenSSL statically"):
        verify_sidecar_build._verify_cryptography_linkage(tmp_path, "x86_64-apple-darwin")


def test_source_build_linkage_gate_accepts_self_contained_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extension = tmp_path / "cryptography" / "hazmat" / "bindings" / "_rust.abi3.so"
    extension.parent.mkdir(parents=True)
    extension.write_bytes(b"native-extension")
    monkeypatch.setattr(
        verify_sidecar_build,
        "_macos_dependencies",
        lambda _extension: ("/usr/lib/libSystem.B.dylib",),
    )

    verify_sidecar_build._verify_cryptography_linkage(tmp_path, "x86_64-apple-darwin")


@pytest.mark.parametrize(
    ("target", "machine", "wrong_machine"),
    (
        ("x86_64-pc-windows-msvc", 0x8664, 0xAA64),
        ("aarch64-pc-windows-msvc", 0xAA64, 0x8664),
    ),
)
def test_windows_sidecar_machine_must_match_release_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    machine: int,
    wrong_machine: int,
) -> None:
    image = SimpleNamespace(
        FILE_HEADER=SimpleNamespace(Machine=machine),
        OPTIONAL_HEADER=SimpleNamespace(Subsystem=2),
        close=lambda: None,
    )
    monkeypatch.setitem(
        sys.modules,
        "pefile",
        SimpleNamespace(PE=lambda _path, fast_load: image),
    )

    verify_sidecar_build._verify_windows_subsystem(tmp_path / "sidecar.exe", target)
    image.FILE_HEADER.Machine = wrong_machine
    with pytest.raises(RuntimeError, match="architecture does not match"):
        verify_sidecar_build._verify_windows_subsystem(tmp_path / "sidecar.exe", target)


def test_native_dependency_installation_is_fail_fast_on_powershell() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "- name: Install locked dependencies\n" not in text
    for name, command in (
        (
            "Install locked Python production dependencies",
            "run: python -m pip install --require-hashes -r requirements.lock",
        ),
        (
            "Install locked Python packaging dependencies",
            "run: python -m pip install --require-hashes -r requirements-tooling.lock",
        ),
        ("Install locked frontend dependencies", "run: npm ci --prefix frontend"),
        ("Verify locked Rust dependency graph", "cargo metadata --manifest-path"),
    ):
        assert f"- name: {name}" in text
        assert command in text


def test_tag_publications_share_one_group_without_cancelling_the_running_tag() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert (
        "group: desktop-${{ github.workflow }}-${{ "
        "github.ref_type == 'tag' && 'tag-publication' || github.ref }}" in text
    )
    assert "cancel-in-progress: ${{ github.ref_type != 'tag' }}" in text
    assert "desktop-${{ github.workflow }}-${{ github.ref }}" not in text


def test_release_commands_quote_github_metadata_from_environment() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    for binding in (
        "RELEASE_COMMIT: ${{ github.sha }}",
        "RELEASE_REPOSITORY: ${{ github.repository }}",
        "RELEASE_TAG: ${{ github.ref_name }}",
    ):
        assert binding in text
    for unsafe_argument in (
        "--commit ${{ github.sha }}",
        "--repo ${{ github.repository }}",
        "--tag ${{ github.ref_name }}",
        "--expected-tag ${{ github.ref_name }}",
    ):
        assert unsafe_argument not in text
    for safe_argument in (
        '--commit "$RELEASE_COMMIT"',
        '--repo "$RELEASE_REPOSITORY"',
        '--tag "$RELEASE_TAG"',
        '--expected-tag "$RELEASE_TAG"',
    ):
        assert safe_argument in text


def test_release_workflow_avoids_publishable_dependency_caches_and_shell_interpolation() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)

    assert "\n          cache:" not in text
    assert "cache-dependency-path:" not in text
    assert text.count("package-manager-cache: false") == 2
    interpolated_run_steps = [
        (job_name, step.get("name"))
        for job_name, job in workflow["jobs"].items()
        for step in job.get("steps", [])
        if "${{" in str(step.get("run", ""))
    ]
    assert interpolated_run_steps == []

    for binding in (
        "AGENT_WHEEL_NAME: ${{ needs.agent-build.outputs.wheel-name }}",
        "NATIVE_TARGET: ${{ matrix.target }}",
        "EXPECTED_RELEASE_DATE: ${{ env.RELEASE_DATE }}",
        "RELEASE_VERSION: ${{ steps.release-version.outputs.value }}",
    ):
        assert binding in text
    for quoted_argument in (
        '--wheel "agent-candidate/$AGENT_WHEEL_NAME"',
        '--target "$NATIVE_TARGET"',
        '--release-date "$EXPECTED_RELEASE_DATE"',
        "careeros-backend-${RELEASE_VERSION}.cdx.json",
    ):
        assert quoted_argument in text

    assert "Read-only baseline for build, smoke, and assembly jobs" in text
    assert "Required for keyless Sigstore identity in actions/attest" in text


def test_required_check_is_emitted_for_every_pull_request() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    pull_request_trigger = text.index("  pull_request:")
    push_trigger = text.index("  push:", pull_request_trigger)
    trigger_config = text[pull_request_trigger:push_trigger]

    assert trigger_config.strip() == "pull_request:"
    assert "paths:" not in trigger_config
    assert "paths-ignore:" not in trigger_config


def test_pull_requests_run_a_real_linux_x64_package_smoke() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    targets = json.loads(NATIVE_TARGETS.read_text(encoding="utf-8"))["include"]

    assert len(targets) == 6
    assert [target for target in targets if target["pullRequest"]] == [
        {
            "label": "Linux x64",
            "runner": "ubuntu-24.04",
            "target": "x86_64-unknown-linux-gnu",
            "bundles": "appimage,deb",
            "pullRequest": True,
        }
    ]
    assert "native-matrix: ${{ steps.native-matrix.outputs.matrix }}" in workflow
    assert 'if os.environ["GITHUB_EVENT_NAME"] == "pull_request":' in workflow
    assert "matrix: ${{ fromJSON(needs.supply-chain.outputs.native-matrix) }}" in workflow
    assert "if: github.event_name != 'pull_request'\n    needs: supply-chain" not in workflow


def test_native_builds_are_pinned_to_the_source_commit_timestamp() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    native = text[text.index("  native:") : text.index("  assemble-release:")]

    assert native.count("Pin native build timestamp to the source commit") == 1
    assert (
        'source_date_epoch="$(git show -s --format=%ct "${RELEASE_COMMIT}^{commit}")"'
    ) in native
    assert 'printf \'SOURCE_DATE_EPOCH=%s\\n\' "$source_date_epoch" >> "$GITHUB_ENV"' in native
    assert native.index("Pin native build timestamp") < native.index(
        "Freeze and smoke-test local backend"
    )


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
    native = text[text.index("  native:") : text.index("  assemble-release:")]

    assert "scripts.release_candidate stage" in text
    assert "scripts.release_candidate stage-agent" in text
    assert "scripts.release_candidate assemble" in text
    assert "scripts.release_candidate verify" in text
    assert native.index("python -m scripts.smoke_native_bundle") < native.index(
        "scripts.release_candidate stage"
    )
    assert "merge-multiple: true" not in text
    assert "--clobber" not in text
    assert "gh release create" not in text
    assert "gh release upload" not in text
    assert "subject-checksums: release-assets/SHA256SUMS" in text
    assert text.count("sbom-path:") == 4
    assert "https://cyclonedx.org/bom" in text
    assert "scripts.verify_sbom_attestations" in text
    assert "--deny-self-hosted-runners" in text


def test_agent_release_wheel_is_built_once_then_smoked_without_rebuilding() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    agent_build = text[text.index("  agent-build:") : text.index("  agent-smoke:")]
    agent_smoke = text[text.index("  agent-smoke:") : text.index("  native:")]
    assemble = text[text.index("  assemble-release:") : text.index("  attest-publish:")]

    assert text.count("python -m pip wheel") == 1
    assert "--no-build-isolation" in agent_build
    assert "--no-deps" in agent_build
    assert "requirements-tooling.lock" in agent_build
    assert (
        'source_date_epoch="$(git show -s --format=%ct "${GITHUB_SHA}^{commit}")"'
    ) in agent_build
    assert 'export SOURCE_DATE_EPOCH="$source_date_epoch"' in agent_build
    assert "name: agent-release-candidate" in agent_build
    assert "scripts.release_candidate stage-agent" in agent_build
    assert "--build-wheel" not in agent_smoke
    assert "name: agent-release-candidate" in agent_smoke
    assert "needs.agent-build.outputs.wheel-name" in agent_smoke
    assert "--requirements-lock agent-candidate/requirements.lock" in agent_smoke
    for runner in ("ubuntu-24.04", "windows-2025", "macos-15"):
        assert runner in agent_smoke
    assert agent_smoke.count('python: "3.12"') == 3
    assert agent_smoke.count('python: "3.13"') == 3

    assert "needs: [supply-chain, agent-build, agent-smoke, native]" in assemble
    assert "name: agent-release-candidate" in assemble
    assert "--agent-root release-staging/agent" in assemble
    assert "--agent-checksums release-attestation/agent-subjects.sha256" in assemble


def test_release_contract_jobs_install_the_locked_parser_dependencies() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assemble = text[text.index("  assemble-release:") : text.index("  attest-publish:")]
    publisher = text[text.index("  attest-publish:") :]
    install = "python -m pip install --require-hashes --requirement requirements-tooling.lock"

    assert install in assemble
    assert install in publisher
    assert publisher.index("scripts.verify_release_source") < publisher.index(install)
    assert publisher.index(install) < publisher.index("scripts.release_candidate verify")


def test_agent_wheel_digest_is_stable_across_source_mtimes(tmp_path: Path) -> None:
    source_date_epoch = "1700000000"
    source_paths = ("backend", "desktop")
    project_files = ("LICENSE", "THIRD_PARTY_NOTICES.txt", "README.md", "pyproject.toml")

    def build_with_mtime(label: str, mtime: int) -> str:
        source_root = tmp_path / f"source-{label}"
        wheel_root = tmp_path / f"wheel-{label}"
        source_root.mkdir()
        wheel_root.mkdir()

        for relative in source_paths:
            shutil.copytree(
                ROOT / relative,
                source_root / relative,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        for relative in project_files:
            shutil.copy2(ROOT / relative, source_root / relative)
        for path in sorted(source_root.rglob("*"), reverse=True):
            os.utime(path, (mtime, mtime))

        environment = os.environ.copy()
        environment.update(
            {
                "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                "PIP_NO_CACHE_DIR": "1",
                "PIP_NO_INDEX": "1",
                "SOURCE_DATE_EPOCH": source_date_epoch,
            }
        )
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-build-isolation",
                "--no-deps",
                "--no-index",
                "--wheel-dir",
                str(wheel_root),
                str(source_root),
            ],
            check=False,
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        wheels = list(wheel_root.glob("*.whl"))
        assert len(wheels) == 1
        return hashlib.sha256(wheels[0].read_bytes()).hexdigest()

    earlier_digest = build_with_mtime("earlier", 946684800)
    later_digest = build_with_mtime("later", 1893456000)

    assert earlier_digest == later_digest


def test_agent_wheel_receives_provenance_and_the_backend_sbom_only() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    publisher = text[text.index("  attest-publish:") :]

    assert "python -m scripts.finalize_backend_sbom" in text
    assert "name: agent-subject-checksums" in publisher
    assert "subject-checksums: release-attestation/agent-subjects.sha256" in publisher
    assert publisher.count("subject-checksums: release-attestation/agent-subjects.sha256") == 1
    assert (
        "sbom-path: release-assets/careeros-backend-"
        "${{ steps.release-version.outputs.value }}.cdx.json"
    ) in publisher
    assert "done < release-attestation/agent-subjects.sha256" in publisher


def test_project_license_and_third_party_notices_are_checked_in_every_native_path() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    config = json.loads(TAURI_CONFIG.read_text(encoding="utf-8"))
    windows_smoke = WINDOWS_SMOKE.read_text(encoding="utf-8")

    assert config["bundle"]["resources"]["../../LICENSE"] == "LICENSE"
    assert (
        config["bundle"]["resources"]["../../THIRD_PARTY_NOTICES.txt"] == "THIRD_PARTY_NOTICES.txt"
    )
    assert "LICENSE text eol=lf" in (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "THIRD_PARTY_NOTICES.txt text eol=lf" in (ROOT / ".gitattributes").read_text(
        encoding="utf-8"
    )
    assert "-IncludeNsisInstall" in workflow
    assert "python -m scripts.smoke_native_bundle --target" in workflow
    assert "python scripts/smoke_native_bundle.py" not in workflow
    assert "Assert-PackagedLicense ($MsiApp.Directory.FullName)" in windows_smoke
    assert "Assert-PackagedLicense ($NsisApp.Directory.FullName)" in windows_smoke
    assert "Assert-PackagedNotices ($MsiApp.Directory.FullName)" in windows_smoke
    assert "Assert-PackagedNotices ($NsisApp.Directory.FullName)" in windows_smoke


def test_package_smokes_require_fresh_frontend_backend_readiness_evidence() -> None:
    windows_smoke = WINDOWS_SMOKE.read_text(encoding="utf-8")
    native_smoke = NATIVE_SMOKE.read_text(encoding="utf-8")
    lifecycle = (ROOT / "frontend" / "src-tauri" / "src" / "lifecycle.rs").read_text(
        encoding="utf-8"
    )

    marker = ".careeros-desktop-ready-v1"
    payload = "backend-ready+frontend-committed"
    for source in (windows_smoke, native_smoke, lifecycle):
        assert marker in source
        assert payload in source
    assert "Remove-Item -LiteralPath $ReadinessEvidence -Force -ErrorAction Stop" in windows_smoke
    assert "Could not clear stale desktop readiness evidence" in windows_smoke
    assert "readiness_evidence.unlink(missing_ok=True)" in native_smoke
    assert ".create_new(true)" in lifecycle


def test_package_smokes_verify_sidecar_cleanup_on_failure_paths() -> None:
    windows_smoke = WINDOWS_SMOKE.read_text(encoding="utf-8")
    native_smoke = NATIVE_SMOKE.read_text(encoding="utf-8")

    assert "function Wait-PackagedSidecarExit" in windows_smoke
    assert "Wait-PackagedSidecarExit $DataDirectory" in windows_smoke
    assert "[StringComparison]::OrdinalIgnoreCase" in windows_smoke
    assert "$null -ne $Process -and -not $Process.HasExited" in windows_smoke
    assert 'Assert-RegularDirectory $SmokeRoot "Installer smoke root"' in windows_smoke
    install_root_assignment = windows_smoke.index("$NsisInstallRoot = $InstallRoot")
    nsis_start = windows_smoke.index("$NsisInstall = Start-Process")
    nsis_exit_check = windows_smoke.index("if ($NsisInstall.ExitCode -ne 0)")
    assert install_root_assignment < nsis_start < nsis_exit_check
    assert windows_smoke.count("$NsisInstallRoot = $InstallRoot") == 1
    assert "$NsisUninstallCompleted = $true" in windows_smoke
    assert "if ($null -ne $NsisInstallRoot -and -not $NsisUninstallCompleted)" in windows_smoke
    assert "$PartialUninstallers.Count -eq 1" in windows_smoke
    assert "if ($null -ne $NsisUninstaller)" in windows_smoke
    assert "NSIS failure cleanup failed with code" in windows_smoke
    assert "def _wait_for_no_orphan" in native_smoke
    assert "finally:\n        _wait_for_no_orphan(data_directory)" in native_smoke
