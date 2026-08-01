from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import tomllib
import zipfile
from pathlib import Path

from scripts.agent_distribution import canonical_agent_wheel_name, stage_agent_candidate
from scripts.check_release_versions import ROOT
from scripts.finalize_backend_sbom import finalize_backend_sbom, locked_requirements
from scripts.release_assets import TARGETS, stage_target_candidate
from scripts.release_contract import EVIDENCE_FILES, assemble_release_bundle

VERSION = "1.3.0"
COMMIT = "a" * 40
RELEASE_DATE = "2026-07-22"


def write_evidence(path: Path) -> Path:
    path.mkdir(parents=True)
    cyclonedx = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "components": [],
    }
    for name in EVIDENCE_FILES:
        destination = path / name
        if name.endswith("-sbom.cdx.json"):
            payload: object = cyclonedx
        elif name.endswith(".json"):
            payload = {"evidence": name}
        else:
            destination.write_text(f"evidence for {name}\n", encoding="utf-8")
            continue
        destination.write_text(json.dumps(payload), encoding="utf-8")
    backend_sbom = path / "backend-sbom.cdx.json"
    backend_sbom.write_text(
        json.dumps(
            {
                "bomFormat": "CycloneDX",
                "specVersion": "1.6",
                "components": [
                    {
                        "type": "library",
                        "name": requirement.name,
                        "version": requirement.version,
                        "bom-ref": f"fixture:{index}",
                    }
                    for index, requirement in enumerate(
                        locked_requirements(ROOT / "requirements.lock").values()
                    )
                ],
            }
        ),
        encoding="utf-8",
    )
    finalize_backend_sbom(
        backend_sbom,
        version=VERSION,
        requirements_lock=ROOT / "requirements.lock",
    )
    return path


def write_native_candidates(path: Path) -> Path:
    path.mkdir(parents=True)
    for index, (target, spec) in enumerate(TARGETS.items()):
        bundle = path / f"raw-{target}"
        bundle.mkdir()
        for package_index, package in enumerate(spec.packages):
            (bundle / f"upstream-{package_index}{package.suffix}").write_bytes(
                f"{index}:{package.name}".encode()
            )
        output = path / target
        stage_target_candidate(
            bundle_root=bundle,
            output=output,
            target=target,
            version=VERSION,
            source_commit=COMMIT,
        )
    return path


def write_agent_wheel(path: Path) -> Path:
    path.mkdir(parents=True)
    with (ROOT / "pyproject.toml").open("rb") as source:
        project = tomllib.load(source)["project"]
    prefix = f"careeros_local-{VERSION}.dist-info/"
    entries = {
        "backend/ai/fixtures/golden-1.0.0.json": b'{"cases":[]}\n',
        "backend/ai/fixtures/golden-1.1.0.json": b'{"cases":[]}\n',
        "backend/automation/cli.py": b"def main():\n    return 0\n",
        "backend/automation/mcp_server.py": b"def main():\n    return 0\n",
        "backend/data/skill_taxonomy.json": b'{"skills":["python"]}\n',
        "backend/inference/model_catalog.json": b'{"models":[]}\n',
        "backend/inference/model_catalog.sha256": b"0" * 64 + b"\n",
        "backend/migrations/alembic.ini": b"[alembic]\nscript_location = %(here)s\n",
        "backend/migrations/script.py.mako": b'"""${message}"""\n',
        "desktop/backend_main.py": b"def main():\n    return 0\n",
        prefix + "METADATA": (
            "Metadata-Version: 2.4\n"
            "Name: careeros-local\n"
            f"Version: {VERSION}\n"
            "License-Expression: MIT\n"
            f"Requires-Python: {project['requires-python']}\n"
            + "".join(f"Requires-Dist: {dependency}\n" for dependency in project["dependencies"])
            + "\n"
        ).encode(),
        prefix + "WHEEL": (
            "Wheel-Version: 1.0\n"
            "Generator: CareerOS release contract test\n"
            "Root-Is-Purelib: true\n"
            "Tag: py3-none-any\n\n"
        ).encode(),
        prefix + "entry_points.txt": (
            "[console_scripts]\n"
            "careeros = backend.automation.cli:main\n"
            "careeros-mcp = backend.automation.mcp_server:main\n"
        ).encode(),
        prefix + "licenses/LICENSE": (ROOT / "LICENSE").read_bytes().replace(b"\r\n", b"\n"),
        prefix + "licenses/THIRD_PARTY_NOTICES.txt": (ROOT / "THIRD_PARTY_NOTICES.txt")
        .read_bytes()
        .replace(b"\r\n", b"\n"),
    }
    for migration in sorted((ROOT / "backend/migrations/versions").glob("*.py")):
        entries[migration.relative_to(ROOT).as_posix()] = migration.read_bytes()
    record_name = prefix + "RECORD"
    record_output = io.StringIO()
    writer = csv.writer(record_output, lineterminator="\n")
    for name, payload in sorted(entries.items()):
        digest = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).rstrip(b"=")
        writer.writerow((name, "sha256=" + digest.decode("ascii"), str(len(payload))))
    writer.writerow((record_name, "", ""))
    entries[record_name] = record_output.getvalue().encode()
    wheel = path / canonical_agent_wheel_name(VERSION)
    with zipfile.ZipFile(wheel, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in sorted(entries.items()):
            archive.writestr(name, payload)
    return wheel


def write_agent_candidate(path: Path) -> Path:
    wheel_root = path / "raw-agent"
    write_agent_wheel(wheel_root)
    output = path / "agent"
    stage_agent_candidate(
        wheel_root=wheel_root,
        requirements_lock=ROOT / "requirements.lock",
        output=output,
        version=VERSION,
        source_commit=COMMIT,
        project_root=ROOT,
    )
    return output


def write_release_bundle(tmp_path: Path, license_path: Path) -> tuple[Path, Path, Path]:
    native = write_native_candidates(tmp_path / "native")
    agent = write_agent_candidate(tmp_path)
    evidence = write_evidence(tmp_path / "evidence")
    output = tmp_path / "release"
    native_checksums = tmp_path / "attestation" / "native-subjects.sha256"
    agent_checksums = tmp_path / "attestation" / "agent-subjects.sha256"
    assemble_release_bundle(
        native_root=native,
        agent_root=agent,
        evidence_root=evidence,
        output=output,
        native_checksums=native_checksums,
        agent_checksums=agent_checksums,
        version=VERSION,
        source_commit=COMMIT,
        release_date=RELEASE_DATE,
        license_path=license_path,
        project_root=ROOT,
    )
    return output, native_checksums, agent_checksums
