from __future__ import annotations

import io
import json
import urllib.error
from datetime import date
from pathlib import Path

import pytest

from scripts import check_frontend_security_exceptions as policy
from scripts.check_frontend_security_exceptions import (
    ROOT,
    collect_advisories,
    patched_version_available,
    validate_policy,
)
from scripts.release_contract import EVIDENCE_FILES


def audit_payload() -> dict:
    return {
        "auditReportVersion": 2,
        "vulnerabilities": {
            "react-router": {
                "severity": "high",
                "nodes": ["node_modules/react-router"],
                "via": [
                    {
                        "name": "react-router",
                        "dependency": "react-router",
                        "severity": "high",
                        "url": "https://github.com/advisories/GHSA-qwww-vcr4-c8h2",
                    }
                ],
            },
            "react-router-dom": {
                "severity": "high",
                "nodes": ["node_modules/react-router-dom"],
                "via": ["react-router"],
            },
        },
        "metadata": {
            "vulnerabilities": {
                "high": 2,
                "critical": 0,
            }
        },
    }


def manifest() -> dict:
    return json.loads((ROOT / "frontend-security-exceptions.json").read_text(encoding="utf-8"))


def test_current_frontend_exceptions_are_exact_guarded_and_time_bounded():
    accepted = validate_policy(
        audit_payload(),
        manifest(),
        today=date(2026, 7, 24),
        registry_checker=lambda _package, _version: False,
    )
    assert accepted == ["GHSA-qwww-vcr4-c8h2"]


def test_postcss_is_patched_and_the_exception_manifest_is_release_evidence():
    lock = json.loads((ROOT / "frontend/package-lock.json").read_text(encoding="utf-8"))
    package = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))

    assert lock["packages"]["node_modules/postcss"]["version"] == "8.5.18"
    assert lock["packages"]["node_modules/postcss"]["dev"] is True
    assert package["overrides"]["postcss"] == "8.5.18"
    assert "frontend-security-exceptions.json" in EVIDENCE_FILES


def test_ci_and_release_preserve_full_audit_before_enforcing_the_policy():
    for relative in (".github/workflows/ci.yml", ".github/workflows/desktop-release.yml"):
        workflow = (ROOT / relative).read_text(encoding="utf-8")
        audit = workflow.index("npm audit --audit-level=high --json")
        copy = workflow.index("cp ../frontend-security-exceptions.json", audit)
        verify = workflow.index("python3 ../scripts/check_frontend_security_exceptions.py", copy)

        assert audit < copy < verify
        assert "frontend-audit.json" in workflow
        assert "frontend-security-exceptions.json" in workflow
        assert "--npm-audit-exit-code" in workflow


def test_unknown_stale_expired_and_patched_advisories_fail_closed():
    payload = audit_payload()
    payload["vulnerabilities"]["unknown"] = {
        "severity": "critical",
        "nodes": ["node_modules/unknown"],
        "via": [
            {
                "name": "unknown",
                "dependency": "unknown",
                "severity": "critical",
                "url": "https://github.com/advisories/GHSA-aaaa-bbbb-cccc",
            }
        ],
    }
    payload["metadata"]["vulnerabilities"]["critical"] = 1
    with pytest.raises(RuntimeError, match="unknown=.*GHSA-aaaa-bbbb-cccc"):
        validate_policy(
            payload,
            manifest(),
            today=date(2026, 7, 24),
            registry_checker=lambda _package, _version: False,
        )

    with pytest.raises(RuntimeError, match="expired on 2026-07-31"):
        validate_policy(
            audit_payload(),
            manifest(),
            today=date(2026, 7, 31),
            registry_checker=lambda _package, _version: False,
        )

    with pytest.raises(RuntimeError, match="is now available"):
        validate_policy(
            audit_payload(),
            manifest(),
            today=date(2026, 7, 24),
            registry_checker=lambda package, _version: package == "react-router-dom",
        )


def test_audit_chains_resolve_to_the_originating_advisory():
    advisories = collect_advisories(audit_payload())
    assert advisories == {
        "GHSA-qwww-vcr4-c8h2": {
            "dependency": "react-router",
            "severity": "high",
        },
    }


def test_postcss_exception_cannot_be_reintroduced():
    payload = audit_payload()
    payload["vulnerabilities"]["postcss"] = {
        "severity": "high",
        "nodes": ["node_modules/postcss"],
        "via": [
            {
                "name": "postcss",
                "dependency": "postcss",
                "severity": "high",
                "url": "https://github.com/advisories/GHSA-r28c-9q8g-f849",
            }
        ],
    }
    payload["metadata"]["vulnerabilities"]["high"] = 3
    with pytest.raises(RuntimeError, match="unknown=.*GHSA-r28c-9q8g-f849"):
        validate_policy(
            payload,
            manifest(),
            today=date(2026, 7, 24),
            registry_checker=lambda _package, _version: False,
        )


def test_rsc_guard_rejects_server_component_markers(tmp_path: Path):
    project = tmp_path / "project"
    source = project / "frontend/src"
    source.mkdir(parents=True)
    (project / "frontend/package.json").write_text(
        json.dumps({"dependencies": {}, "devDependencies": {}}),
        encoding="utf-8",
    )
    (project / "frontend/package-lock.json").write_text(
        json.dumps(
            {
                "packages": {
                    "node_modules/react-router": {
                        "version": "7.18.1",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (source / "main.jsx").write_text(
        "import { createRoot } from 'react-dom/client';\ncreateRoot(root).render(app);\n",
        encoding="utf-8",
    )
    (source / "server.jsx").write_text(
        'import { RSCStaticRouter } from "react-router/rsc";\n',
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="RSC guard failed"):
        validate_policy(
            audit_payload(),
            manifest(),
            root=project,
            today=date(2026, 7, 24),
            registry_checker=lambda _package, _version: False,
        )


class RegistryResponse(io.BytesIO):
    def __init__(self, payload: bytes, *, status: int = 200):
        super().__init__(payload)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, _type, _value, _traceback):
        self.close()


def test_registry_probe_requires_matching_metadata_and_readable_tarball(monkeypatch):
    responses = iter(
        (
            RegistryResponse(
                json.dumps(
                    {
                        "name": "react-router-dom",
                        "version": "8.3.0",
                        "dist": {
                            "integrity": "sha512-test",
                            "tarball": (
                                "https://registry.npmjs.org/react-router-dom/-/"
                                "react-router-dom-8.3.0.tgz"
                            ),
                        },
                    }
                ).encode()
            ),
            RegistryResponse(b"x", status=206),
        )
    )
    monkeypatch.setattr(policy.urllib.request, "urlopen", lambda *_args, **_kwargs: next(responses))

    assert patched_version_available("react-router-dom", "8.3.0") is True


def test_registry_probe_rejects_false_positive_metadata(monkeypatch):
    response = RegistryResponse(b'{"error":"version not found: 8.3.0"}')
    monkeypatch.setattr(policy.urllib.request, "urlopen", lambda *_args, **_kwargs: response)

    with pytest.raises(RuntimeError, match="mismatched metadata"):
        patched_version_available("react-router-dom", "8.3.0")


def test_registry_probe_treats_exact_version_404_as_unavailable(monkeypatch):
    def missing(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            "https://registry.npmjs.org/react-router-dom/8.3.0",
            404,
            "Not Found",
            {},
            None,
        )

    monkeypatch.setattr(policy.urllib.request, "urlopen", missing)

    assert patched_version_available("react-router-dom", "8.3.0") is False
