from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts import build_backend_sidecar, verify_sidecar_build


def _runtime(root: Path) -> Path:
    runtime = root / "runtime"
    (runtime / "_internal" / "backend").mkdir(parents=True)
    (runtime / build_backend_sidecar.executable_name()).write_bytes(b"executable")
    (runtime / "_internal" / "backend" / "module.py").write_bytes(b"value = 1\n")
    return runtime


def test_runtime_inventory_is_deterministic_and_content_bound(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    first = build_backend_sidecar.runtime_inventory(runtime)

    for path in runtime.rglob("*"):
        os.utime(path, (1_900_000_000, 1_900_000_000))
    second = build_backend_sidecar.runtime_inventory(runtime)
    assert second == first

    module = runtime / "_internal" / "backend" / "module.py"
    module.write_bytes(b"value = 2\n")
    changed = build_backend_sidecar.runtime_inventory(runtime)
    assert changed["runtimeFileCount"] == first["runtimeFileCount"]
    assert changed["runtimeSizeBytes"] == first["runtimeSizeBytes"]
    assert changed["runtimeSha256"] != first["runtimeSha256"]


def test_runtime_inventory_rejects_links(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    linked = runtime / "_internal" / "linked-module.py"
    try:
        linked.symlink_to(runtime / "_internal" / "backend" / "module.py")
    except OSError:
        pytest.skip("The test account cannot create a file symlink")
    try:
        with pytest.raises(RuntimeError, match="symbolic link"):
            build_backend_sidecar.runtime_inventory(runtime)
    finally:
        linked.unlink(missing_ok=True)


def test_prepare_tauri_runtime_writes_a_complete_atomic_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _runtime(tmp_path / "source")
    binaries = tmp_path / "tauri-binaries"
    monkeypatch.setattr(build_backend_sidecar, "TAURI_BINARIES", binaries)
    target = build_backend_sidecar.native_target_triple()

    destination = build_backend_sidecar.prepare_tauri_runtime(source, target)
    manifest_path = binaries / "sidecar-build.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert destination == binaries / "careeros-backend-runtime" / destination.name
    assert set(payload) == verify_sidecar_build.MANIFEST_FIELDS
    assert payload["schemaVersion"] == build_backend_sidecar.SIDECAR_MANIFEST_SCHEMA
    assert payload["layout"] == build_backend_sidecar.RUNTIME_LAYOUT
    assert payload["target"] == target
    assert payload["filename"] == destination.relative_to(binaries).as_posix()
    assert payload["sha256"] == build_backend_sidecar.sha256(destination)
    assert {
        name: payload[name] for name in ("runtimeFileCount", "runtimeSizeBytes", "runtimeSha256")
    } == build_backend_sidecar.runtime_inventory(destination.parent)
    assert not (binaries / "sidecar-build.json.tmp").exists()


def test_manifest_binary_path_is_canonical_and_contained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binaries = tmp_path / "binaries"
    runtime = binaries / "careeros-backend-runtime"
    runtime.mkdir(parents=True)
    target = build_backend_sidecar.native_target_triple()
    binary = runtime / build_backend_sidecar.executable_name()
    binary.write_bytes(b"binary")
    manifest = binaries / "sidecar-build.json"
    manifest.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(verify_sidecar_build, "MANIFEST", manifest)

    assert (
        verify_sidecar_build._contained_manifest_binary(
            {"filename": binary.relative_to(binaries).as_posix()}, target
        )
        == binary.resolve()
    )
    with pytest.raises(RuntimeError, match="not canonical"):
        verify_sidecar_build._contained_manifest_binary({"filename": "../careeros-backend"}, target)


def test_pyinstaller_spec_rejects_linked_runtime_data() -> None:
    text = (build_backend_sidecar.PROJECT_ROOT / "desktop" / "careeros-backend.spec").read_text(
        encoding="utf-8"
    )

    assert "if is_link_like(source_root) or not source_root.is_dir():" in text
    assert "if is_link_like(source):" in text
    assert "source.resolve(strict=True).is_relative_to(resolved_root)" in text
    assert '"providers" / "configuration" / "packs"' in text
    assert '"backend/providers/configuration/packs"' in text
