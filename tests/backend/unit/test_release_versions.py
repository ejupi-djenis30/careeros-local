from pathlib import Path

import pytest

from scripts.check_release_versions import (
    changelog_release_date,
    release_versions,
    validate_release_date,
    validate_versions,
)

ROOT = Path(__file__).resolve().parents[3]


def test_repository_release_versions_are_consistent() -> None:
    versions = release_versions(ROOT)

    assert validate_versions(versions) == "1.11.0"
    assert changelog_release_date("1.11.0", ROOT) == "2026-08-01"
    assert validate_release_date("1.11.0", "2026-08-01", ROOT) == "2026-08-01"
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


def test_release_date_must_match_the_unique_changelog_heading(tmp_path: Path) -> None:
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [1.6.0] - 2026-07-24\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="does not match CHANGELOG.md"):
        validate_release_date("1.6.0", "2026-07-23", tmp_path)

    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [1.6.0] - 2026-07-24\n\n## [1.6.0] - 2026-07-24\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="exactly one dated release heading"):
        validate_release_date("1.6.0", "2026-07-24", tmp_path)
