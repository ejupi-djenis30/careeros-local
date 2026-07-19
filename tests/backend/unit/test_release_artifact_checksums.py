from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from scripts.write_artifact_checksums import release_artifacts


def test_release_artifacts_include_only_flattened_installers() -> None:
    with TemporaryDirectory(prefix="careeros-checksums-") as directory:
        root = Path(directory)
        installers = [
            root / "nsis" / "CareerOS_1.0.1_x64-setup.exe",
            root / "msi" / "CareerOS_1.0.1_x64_en-US.msi",
            root / "dmg" / "CareerOS_1.0.1_x64.dmg",
            root / "appimage" / "CareerOS_1.0.1_amd64.AppImage",
            root / "deb" / "CareerOS_1.0.1_amd64.deb",
        ]
        for path in installers:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(path.name.encode())
        internal = root / "macos" / "CareerOS.app" / "Contents" / "MacOS" / "careeros-local"
        internal.parent.mkdir(parents=True)
        internal.write_bytes(b"not a release asset")

        selected = release_artifacts(root)

        assert {path.name for path in selected} == {path.name for path in installers}
        assert internal not in selected


def test_release_artifacts_reject_duplicate_flattened_names() -> None:
    with TemporaryDirectory(prefix="careeros-checksums-") as directory:
        root = Path(directory)
        for bundle in ("first", "second"):
            path = root / bundle / "CareerOS.dmg"
            path.parent.mkdir(parents=True)
            path.write_bytes(bundle.encode())

        with pytest.raises(RuntimeError, match="duplicate release filenames"):
            release_artifacts(root)
