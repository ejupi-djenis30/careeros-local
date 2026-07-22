from pathlib import Path

import pytest

from scripts.check_release_versions import release_versions, validate_versions

ROOT = Path(__file__).resolve().parents[3]


def test_repository_release_versions_are_consistent() -> None:
    versions = release_versions(ROOT)

    assert validate_versions(versions) == "1.3.0"
    assert len(versions) == 7


def test_version_validation_rejects_drift_and_wrong_tag() -> None:
    with pytest.raises(RuntimeError, match="versions disagree"):
        validate_versions({"python": "1.0.0", "desktop": "1.0.1"})

    with pytest.raises(RuntimeError, match="does not match"):
        validate_versions({"python": "1.0.0"}, "v2.0.0")


@pytest.mark.parametrize("version", ["1.0.0-rc.1", "1.0.0+build.1", "01.0.0"])
def test_version_validation_rejects_nonstable_or_noncanonical_semver(version: str) -> None:
    with pytest.raises(RuntimeError, match="stable SemVer"):
        validate_versions({"python": version})
