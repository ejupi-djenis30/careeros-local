"""Run post-bundle desktop lifecycle checks on macOS and Linux packages."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from scripts.license_contract import find_packaged_license
from scripts.release_assets import TARGETS
from scripts.third_party_notices import find_packaged_notice

ROOT = Path(__file__).resolve().parents[1]
SMOKE_READY_MARKER = ".careeros-desktop-ready-v1"
SMOKE_READY_PAYLOAD = "backend-ready+frontend-committed\n"
DMG_DETACH_RETRY_DELAYS = (1, 2, 4)
ORPHAN_EXIT_TIMEOUT_SECONDS = 35
ORPHAN_POLL_SECONDS = 0.25


def _single(paths: list[Path], label: str) -> Path:
    if len(paths) != 1:
        raise RuntimeError(f"Expected exactly one {label}; found {len(paths)}")
    return paths[0]


def _validated_bundle_root(target: str) -> Path:
    spec = TARGETS.get(target)
    if spec is None:
        raise RuntimeError(f"Unsupported native smoke target: {target}")
    host_platform = ""
    if sys.platform == "darwin":
        host_platform = "macos"
    elif sys.platform.startswith("linux"):
        host_platform = "linux"
    else:
        raise RuntimeError("This native bundle smoke supports macOS and Linux only")
    if spec.platform != host_platform:
        raise RuntimeError(
            f"Native smoke target {target} does not match the {host_platform} runner"
        )
    root = (ROOT / "frontend" / "src-tauri" / "target").resolve()
    bundle_root = (root / target / "release" / "bundle").resolve()
    if not bundle_root.is_relative_to(root):
        raise RuntimeError("Native smoke bundle path escapes the Tauri target directory")
    return bundle_root


def _assert_no_orphan(data_directory: Path) -> None:
    completed = subprocess.run(
        ["ps", "-axo", "command="],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    marker = str(data_directory)
    if any("careeros-backend" in line and marker in line for line in completed.stdout.splitlines()):
        raise RuntimeError("Packaged sidecar remained orphaned after native app exit")


def _wait_for_no_orphan(data_directory: Path) -> None:
    deadline = time.monotonic() + ORPHAN_EXIT_TIMEOUT_SECONDS
    last_error: RuntimeError | None = None
    while True:
        try:
            _assert_no_orphan(data_directory)
            return
        except RuntimeError as error:
            last_error = error
        if time.monotonic() >= deadline:
            raise RuntimeError(
                "Packaged sidecar did not exit within the bounded cleanup window"
            ) from last_error
        time.sleep(ORPHAN_POLL_SECONDS)


def _run_application(command: list[str], data_directory: Path, *, offline: bool = False) -> None:
    readiness_evidence = data_directory / SMOKE_READY_MARKER
    readiness_evidence.unlink(missing_ok=True)
    environment = os.environ.copy()
    environment["CAREEROS_DESKTOP_SMOKE"] = "1"
    environment["CAREEROS_DESKTOP_SMOKE_DATA_DIR"] = str(data_directory)
    if offline:
        environment["OFFLINE_MODE"] = "true"
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=150,
            check=False,
        )
        if completed.returncode != 0:
            safe_error = (completed.stderr or completed.stdout)[-3000:]
            raise RuntimeError(
                f"Native package smoke exited with {completed.returncode}: {safe_error}"
            )
        if (
            not readiness_evidence.is_file()
            or readiness_evidence.read_text(encoding="utf-8") != SMOKE_READY_PAYLOAD
        ):
            raise RuntimeError(
                "Native package smoke did not complete the frontend/backend readiness handshake"
            )
        database = data_directory / "vault" / "careeros.db"
        if not database.is_file() or database.stat().st_size == 0:
            raise RuntimeError("Native package smoke did not initialize the career vault")
    finally:
        _wait_for_no_orphan(data_directory)


def _run_reopen(command: list[str], data_directory: Path) -> None:
    _run_application(command, data_directory)
    marker = data_directory / "vault" / "smoke-preserve.marker"
    marker_value = "careeros-vault-preservation-v1"
    marker.write_text(marker_value, encoding="utf-8")
    _run_application(command, data_directory, offline=True)
    if marker.read_text(encoding="utf-8") != marker_value:
        raise RuntimeError("Offline reopen did not preserve the existing user vault marker")


def _run_export_smoke(binary: Path, data_directory: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "smoke_packaged_backend.py"),
            "--binary",
            str(binary),
            "--data-dir",
            str(data_directory),
        ],
        cwd=ROOT,
        check=True,
        timeout=180,
    )


def _require_distribution_licenses(package_root: Path, label: str) -> tuple[Path, Path]:
    try:
        license_path, _license_record = find_packaged_license(package_root)
        notice_path, _notice_record = find_packaged_notice(package_root)
    except RuntimeError as error:
        raise RuntimeError(f"{label} license/notice verification failed: {error}") from error
    return license_path, notice_path


def _detach_mounted_dmg(mount_point: Path) -> None:
    command = ["hdiutil", "detach", str(mount_point)]
    for delay in (*DMG_DETACH_RETRY_DELAYS, None):
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if completed.returncode == 0:
            return
        if delay is not None:
            time.sleep(delay)

    subprocess.run(
        ["hdiutil", "detach", "-force", str(mount_point)],
        check=True,
        timeout=120,
    )


@contextmanager
def _mounted_read_only_dmg(dmg: Path, mount_point: Path) -> Iterator[Path]:
    subprocess.run(
        ["hdiutil", "verify", str(dmg)],
        check=True,
        timeout=120,
    )
    mount_point.mkdir()
    subprocess.run(
        [
            "hdiutil",
            "attach",
            "-readonly",
            "-nobrowse",
            "-noautoopen",
            "-mountpoint",
            str(mount_point),
            str(dmg),
        ],
        check=True,
        timeout=120,
    )
    try:
        yield mount_point
    finally:
        _detach_mounted_dmg(mount_point)


def _macos(bundle_root: Path, smoke_root: Path) -> int:
    _single(list((bundle_root / "macos").glob("*.app")), "macOS app bundle")
    dmg = _single(list((bundle_root / "dmg").glob("*.dmg")), "macOS DMG")
    with _mounted_read_only_dmg(dmg, smoke_root / "dmg-mount") as mounted:
        app = _single(list(mounted.glob("*.app")), "mounted macOS app bundle")
        _require_distribution_licenses(app / "Contents" / "Resources", "mounted macOS DMG")
        executable = _single(
            [path for path in (app / "Contents" / "MacOS").iterdir() if path.is_file()],
            "mounted macOS application executable",
        )
        data_directory = smoke_root / "macos-data"
        sidecar = _single(
            list((app / "Contents" / "Resources").rglob("careeros-backend")),
            "mounted macOS packaged backend",
        )
        _run_export_smoke(sidecar, data_directory)
        _run_reopen([str(executable)], data_directory)
    return 1


def _linux(bundle_root: Path, smoke_root: Path) -> int:
    appimage = _single(list((bundle_root / "appimage").glob("*.AppImage")), "AppImage")
    deb = _single(list((bundle_root / "deb").glob("*.deb")), "Debian package")
    appimage.chmod(appimage.stat().st_mode | 0o111)
    extracted = smoke_root / "appimage-extracted"
    extracted.mkdir()
    subprocess.run(
        [str(appimage), "--appimage-extract"],
        cwd=extracted,
        check=True,
        timeout=120,
        stdout=subprocess.DEVNULL,
    )
    appimage_sidecar = _single(
        list(extracted.rglob("careeros-backend")), "AppImage packaged backend"
    )
    _require_distribution_licenses(
        appimage_sidecar.parent.parent, "extracted AppImage resource directory"
    )
    appimage_data = smoke_root / "appimage-data"
    _run_export_smoke(appimage_sidecar, appimage_data)
    appimage_command = [str(appimage)]
    if not os.environ.get("DISPLAY"):
        xvfb = shutil.which("xvfb-run")
        if not xvfb:
            raise RuntimeError("xvfb-run is required for headless Linux native smoke")
        appimage_command = [xvfb, "-a", *appimage_command]
    environment_value = os.environ.get("APPIMAGE_EXTRACT_AND_RUN")
    os.environ["APPIMAGE_EXTRACT_AND_RUN"] = "1"
    try:
        _run_reopen(appimage_command, appimage_data)
    finally:
        if environment_value is None:
            os.environ.pop("APPIMAGE_EXTRACT_AND_RUN", None)
        else:
            os.environ["APPIMAGE_EXTRACT_AND_RUN"] = environment_value

    deb_root = smoke_root / "deb-root"
    subprocess.run(["dpkg-deb", "-x", str(deb), str(deb_root)], check=True, timeout=60)
    executable = _single(list((deb_root / "usr" / "bin").glob("careeros-local*")), "DEB app")
    deb_sidecar = _single(list(deb_root.rglob("careeros-backend")), "DEB packaged backend")
    _require_distribution_licenses(deb_sidecar.parent.parent, "extracted Debian resource directory")
    deb_command = [str(executable)]
    if not os.environ.get("DISPLAY"):
        deb_command = [shutil.which("xvfb-run") or "xvfb-run", "-a", *deb_command]
    deb_data = smoke_root / "deb-data"
    _run_export_smoke(deb_sidecar, deb_data)
    _run_reopen(deb_command, deb_data)
    return 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    arguments = parser.parse_args()
    bundle_root = _validated_bundle_root(arguments.target)
    with tempfile.TemporaryDirectory(prefix="careeros-native-") as directory:
        smoke_root = Path(directory).resolve()
        checked = (
            _macos(bundle_root, smoke_root)
            if sys.platform == "darwin"
            else _linux(bundle_root, smoke_root)
        )
    print(f"NATIVE_BUNDLE_SMOKE=PASS TARGET={arguments.target} PACKAGES={checked}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
