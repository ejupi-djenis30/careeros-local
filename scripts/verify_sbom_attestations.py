"""Prove that gh verified every expected CycloneDX predicate for one subject."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

CYCLONEDX_PREDICATE = "https://cyclonedx.org/bom"


def _canonical(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def verified_predicates(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not value:
        raise RuntimeError("GitHub CLI returned no verified SBOM attestations")
    predicates: list[dict[str, Any]] = []
    for entry in value:
        if not isinstance(entry, dict):
            raise RuntimeError("GitHub CLI attestation result is not an object")
        verification = entry.get("verificationResult")
        if not isinstance(verification, dict):
            raise RuntimeError("GitHub CLI result has no verification result")
        statement = verification.get("statement")
        if not isinstance(statement, dict) or statement.get("predicateType") != CYCLONEDX_PREDICATE:
            raise RuntimeError("GitHub CLI result has an unexpected predicate type")
        predicate = statement.get("predicate")
        if not isinstance(predicate, dict):
            raise RuntimeError("Verified CycloneDX predicate is not an object")
        predicates.append(predicate)
    return predicates


def require_exact_sboms(verification_json: Path, sbom_paths: list[Path]) -> None:
    if len(sbom_paths) != 3:
        raise RuntimeError("Exactly three component SBOMs are required")
    expected = {_canonical(json.loads(path.read_text(encoding="utf-8"))) for path in sbom_paths}
    if len(expected) != len(sbom_paths):
        raise RuntimeError("Component SBOMs must be distinct")
    actual = {_canonical(predicate) for predicate in verified_predicates(verification_json)}
    if actual != expected:
        raise RuntimeError("Verified SBOM attestations differ from the exact release candidate")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verification-json", required=True, type=Path)
    parser.add_argument("--sbom", required=True, type=Path, action="append")
    arguments = parser.parse_args()
    require_exact_sboms(arguments.verification_json, arguments.sbom)
    print("SBOM_ATTESTATIONS_OK count=3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
