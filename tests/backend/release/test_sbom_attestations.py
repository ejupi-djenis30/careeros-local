from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.verify_sbom_attestations import CYCLONEDX_PREDICATE, require_exact_sboms


def _write_contract(tmp_path: Path) -> tuple[Path, list[Path]]:
    sboms: list[Path] = []
    entries = []
    for index in range(3):
        value = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "components": [{"name": f"component-{index}"}],
        }
        path = tmp_path / f"sbom-{index}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        sboms.append(path)
        entries.append(
            {
                "verificationResult": {
                    "statement": {"predicateType": CYCLONEDX_PREDICATE, "predicate": value}
                }
            }
        )
    verification = tmp_path / "verified.json"
    verification.write_text(json.dumps(entries), encoding="utf-8")
    return verification, sboms


def test_exact_three_verified_sboms_are_required(tmp_path: Path) -> None:
    verification, sboms = _write_contract(tmp_path)

    require_exact_sboms(verification, sboms)

    replacement = json.loads(sboms[0].read_text(encoding="utf-8"))
    replacement["components"][0]["name"] = "tampered"
    sboms[0].write_text(json.dumps(replacement), encoding="utf-8")
    with pytest.raises(RuntimeError, match="differ"):
        require_exact_sboms(verification, sboms)


def test_empty_or_wrong_predicate_verification_fails_closed(tmp_path: Path) -> None:
    verification, sboms = _write_contract(tmp_path)
    verification.write_text("[]", encoding="utf-8")
    with pytest.raises(RuntimeError, match="no verified"):
        require_exact_sboms(verification, sboms)

    verification.write_text(
        json.dumps(
            [
                {
                    "verificationResult": {
                        "statement": {"predicateType": "foreign", "predicate": {}}
                    }
                }
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="unexpected predicate"):
        require_exact_sboms(verification, sboms)
