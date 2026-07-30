from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.finalize_backend_sbom import (
    finalize_backend_sbom,
    project_bom_ref,
    validate_backend_sbom,
)

VERSION = "1.10.0"
HASH = "a" * 64


def _write_lock(path: Path, requirement: str = "dependency==1.2.3") -> Path:
    path.write_text(
        f"{requirement} \\\n    --hash=sha256:{HASH}\n",
        encoding="utf-8",
    )
    return path


def _write_dependency_sbom(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "bomFormat": "CycloneDX",
                "specVersion": "1.6",
                "components": [
                    {
                        "type": "library",
                        "name": "dependency",
                        "version": "1.2.3",
                        "bom-ref": "pkg:pypi/dependency@1.2.3",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_backend_sbom_is_bound_to_the_exact_project_and_dependency_graph(
    tmp_path: Path,
) -> None:
    path = _write_dependency_sbom(tmp_path / "backend.cdx.json")
    lock = _write_lock(tmp_path / "requirements.lock")

    finalized = finalize_backend_sbom(path, version=VERSION, requirements_lock=lock)

    assert validate_backend_sbom(finalized, version=VERSION, requirements_lock=lock) == finalized
    assert finalized["metadata"]["component"]["bom-ref"] == project_bom_ref(VERSION)
    assert finalized["components"][0]["purl"] == "pkg:pypi/dependency@1.2.3"
    assert finalized["dependencies"][-1] == {
        "ref": project_bom_ref(VERSION),
        "dependsOn": ["pkg:pypi/dependency@1.2.3"],
    }


def test_backend_sbom_rejects_missing_refs_and_existing_root(tmp_path: Path) -> None:
    lock = _write_lock(tmp_path / "requirements.lock")
    path = tmp_path / "backend.cdx.json"
    path.write_text(
        json.dumps(
            {
                "bomFormat": "CycloneDX",
                "specVersion": "1.6",
                "components": [{"name": "dependency"}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="bom-ref"):
        finalize_backend_sbom(path, version=VERSION, requirements_lock=lock)

    path = _write_dependency_sbom(path)
    finalize_backend_sbom(path, version=VERSION, requirements_lock=lock)
    with pytest.raises(RuntimeError, match="already has a root"):
        finalize_backend_sbom(path, version=VERSION, requirements_lock=lock)


def test_backend_sbom_rejects_root_ref_and_lock_coordinate_mismatches(
    tmp_path: Path,
) -> None:
    lock = _write_lock(tmp_path / "requirements.lock")
    path = _write_dependency_sbom(tmp_path / "backend.cdx.json")
    value = json.loads(path.read_text(encoding="utf-8"))
    value["components"][0]["bom-ref"] = project_bom_ref(VERSION)
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(RuntimeError, match="collides"):
        finalize_backend_sbom(path, version=VERSION, requirements_lock=lock)

    for field, value, message in (
        ("version", "9.9.9", "version"),
        ("purl", "pkg:pypi/dependency@9.9.9", "purl"),
        ("name", "other", "exact requirements lock"),
    ):
        path = _write_dependency_sbom(tmp_path / f"{field}.json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["components"][0][field] = value
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(RuntimeError, match=message):
            finalize_backend_sbom(path, version=VERSION, requirements_lock=lock)


@pytest.mark.parametrize(
    "entry",
    [
        "dependency>=1.2.3 \\\n    --hash=sha256:" + HASH,
        "dependency==1.2.3",
        "dependency==1.2.3 \\\n    --hash=md5:" + ("a" * 32),
        "dependency==1.2.3 \\\n    --hash=sha256:" + HASH + " \\\n",
    ],
    ids=["range", "unhashed", "wrong-algorithm", "unterminated"],
)
def test_requirements_parser_fails_closed(tmp_path: Path, entry: str) -> None:
    lock = tmp_path / "requirements.lock"
    lock.write_text(entry + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="lock|pin"):
        finalize_backend_sbom(
            _write_dependency_sbom(tmp_path / "backend.cdx.json"),
            version=VERSION,
            requirements_lock=lock,
        )


def test_false_marker_is_excluded_like_pip_audit(tmp_path: Path) -> None:
    lock = _write_lock(tmp_path / "requirements.lock")
    lock.write_text(
        lock.read_text(encoding="utf-8")
        + f'other==9.0 ; python_version < "0" \\\n    --hash=sha256:{HASH}\n',
        encoding="utf-8",
    )
    path = _write_dependency_sbom(tmp_path / "backend.cdx.json")
    finalize_backend_sbom(path, version=VERSION, requirements_lock=lock)
