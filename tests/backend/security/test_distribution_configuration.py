from __future__ import annotations

import json
import tomllib
from pathlib import Path

import yaml
from slowapi.util import get_remote_address
from starlette.requests import Request

ROOT = Path(__file__).resolve().parents[3]


def test_container_oci_metadata_matches_release_manifests() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    tauri = json.loads((ROOT / "frontend/src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
    version = pyproject["project"]["version"]

    assert {version, package["version"], tauri["version"]} == {"1.11.1"}
    for path in (ROOT / "Dockerfile", ROOT / "frontend/Dockerfile"):
        dockerfile = path.read_text(encoding="utf-8")
        assert dockerfile.count("ARG CAREEROS_BUILD_REVISION=unknown") == 1
        assert (
            'org.opencontainers.image.source="https://github.com/ejupi-djenis30/careeros-local"'
        ) in dockerfile
        assert f'org.opencontainers.image.version="{version}"' in dockerfile
        assert 'org.opencontainers.image.revision="${CAREEROS_BUILD_REVISION}"' in dockerfile
        assert 'org.opencontainers.image.licenses="MIT"' in dockerfile


def test_dependabot_cools_every_routine_ecosystem_update_for_seven_days() -> None:
    configuration = yaml.safe_load((ROOT / ".github/dependabot.yml").read_text(encoding="utf-8"))
    updates = configuration["updates"]

    assert [(entry["package-ecosystem"], entry["directory"]) for entry in updates] == [
        ("pip", "/"),
        ("npm", "/frontend"),
        ("docker", "/"),
        ("docker", "/frontend"),
        ("docker", "/docker/ollama"),
        ("github-actions", "/"),
    ]
    assert all(entry["cooldown"] == {"default-days": 7} for entry in updates)


def test_frontend_proxy_normalizes_the_backend_host_header() -> None:
    configuration = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            ROOT / "frontend/nginx.conf",
            ROOT / "frontend/nginx-api-proxy.conf",
        )
    )

    assert configuration.count("proxy_set_header Host localhost;") == 1
    assert "proxy_set_header Host $host;" not in configuration


def test_frontend_proxy_scopes_the_larger_portable_archive_body_limit() -> None:
    configuration = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert configuration.count("client_max_body_size 129m;") == 2
    assert configuration.count("client_max_body_size 11m;") == 1
    assert "location = /api/v1/portability/inspect" in configuration
    assert "location = /api/v1/portability/restore" in configuration
    assert configuration.count("include /etc/nginx/conf.d/careeros-api-proxy.inc;") == 3
    assert 'test "$ordinary_status" = "413"' in workflow
    assert "/api/v1/portability/inspect/nested" in workflow
    assert 'test "$nested_status" = "413"' in workflow
    assert 'test "$portable_status" = "502"' in workflow
    assert "error_page 413 = @request_body_too_large;" in configuration
    assert "default_type application/json;" in configuration
    assert (
        'return 413 \'{"detail":"File too large or request body exceeds the local processing limit."}\';'
        in configuration
    )


def test_container_backend_is_private_and_never_trusts_forwarded_client_identity() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    backend = compose["services"]["backend"]
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    desktop_entrypoint = (ROOT / "desktop/backend_main.py").read_text(encoding="utf-8")

    assert backend["expose"] == ["8000"]
    assert "ports" not in backend
    assert '"--no-proxy-headers"' in dockerfile
    assert "--forwarded-allow-ips" not in dockerfile
    assert "proxy_headers=False" in desktop_entrypoint

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": [(b"x-forwarded-for", b"203.0.113.77")],
            "client": ("127.0.0.1", 43111),
            "server": ("127.0.0.1", 8000),
        }
    )
    assert get_remote_address(request) == "127.0.0.1"


def test_backend_container_uses_minimal_alpine_runtime_and_drops_build_tooling() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    backend = compose["services"]["backend"]
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert (
        "FROM python:3.12.14-alpine3.23@sha256:"
        "167bc85084c9df34480efc26b4528fb68feaa8a79183b5658952137025b6f061"
    ) in dockerfile
    assert "addgroup -S -g 10001 careernos" in dockerfile
    assert "adduser -S -D -H -u 10001 -G careernos" in dockerfile
    assert "python -m pip uninstall --yes pip" in dockerfile
    assert "/usr/local/lib/python3.12/ensurepip" in dockerfile
    assert "USER careernos:careernos" in dockerfile
    assert backend["user"] == "10001:10001"
    assert backend["pids_limit"] == 256
    assert backend["stop_grace_period"] == "30s"
    assert backend["read_only"] is True
    assert backend["cap_drop"] == ["ALL"]
    assert backend["security_opt"] == ["no-new-privileges:true"]


def test_compose_services_have_bounded_processes_logs_and_segmented_networks() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    expected_logging = {
        "driver": "json-file",
        "options": {"max-size": "10m", "max-file": "3"},
    }

    assert services["ollama"]["image"] == "careeros-local-ollama:0.33.3-careeros.1"
    assert services["ollama"]["build"] == {
        "context": ".",
        "dockerfile": "docker/ollama/Dockerfile",
    }
    assert services["ollama"]["init"] is True
    assert services["ollama"]["user"] == "10001:10001"
    assert services["ollama"]["depends_on"] == {
        "ollama-volume-init": {"condition": "service_completed_successfully"}
    }
    assert services["ollama"]["volumes"] == [
        "ollama_data:/var/lib/ollama/.ollama"
    ]
    assert services["ollama"]["pids_limit"] == 512
    assert services["ollama"]["read_only"] is True
    assert services["ollama"]["tmpfs"] == ["/tmp:rw,nosuid,nodev,noexec,size=256m,mode=1777"]
    assert services["ollama"]["cap_drop"] == ["ALL"]
    assert services["ollama"]["security_opt"] == ["no-new-privileges:true"]
    assert services["ollama"]["networks"] == ["model"]

    volume_init = services["ollama-volume-init"]
    assert volume_init["image"] == services["ollama"]["image"]
    assert volume_init["user"] == "0:0"
    assert volume_init["read_only"] is True
    assert volume_init["cap_drop"] == ["ALL"]
    assert volume_init["cap_add"] == ["CHOWN"]
    assert volume_init["security_opt"] == ["no-new-privileges:true"]
    assert volume_init["network_mode"] == "none"
    assert volume_init["volumes"] == services["ollama"]["volumes"]
    assert "chown --recursive --no-dereference 10001:10001" in volume_init["command"]

    assert services["backend"]["networks"] == ["app", "model"]
    assert services["frontend"]["networks"] == ["app"]
    assert services["frontend"]["pids_limit"] == 128
    assert services["backend"]["tmpfs"] == ["/tmp:rw,nosuid,nodev,noexec,size=128m,mode=1777"]
    assert services["frontend"]["tmpfs"] == ["/tmp:rw,nosuid,nodev,noexec,size=64m,mode=1777"]
    assert all(service["logging"] == expected_logging for service in services.values())
    assert compose["networks"] == {
        "app": {"name": "careeros-local-app"},
        "model": {"name": "careeros-local-model"},
    }


def test_patched_ollama_source_dependency_graph_and_gate_are_pinned() -> None:
    dockerfile = (ROOT / "docker/ollama/Dockerfile").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert (
        "FROM golang:1.27.1-bookworm@sha256:"
        "648f440f42a0958804efb24df176f806f9d353b41f1c0627f666428e40310f6b"
    ) in dockerfile
    assert (
        "FROM ollama/ollama:0.33.3@sha256:"
        "32931b46719f673c05fdbaa81ccb26da18ea4a1c57590a754874ab28ba269eb2"
    ) in dockerfile
    assert (
        "https://github.com/ollama/ollama/archive/"
        "b79067b0db7417f20108363bc22adb97f35c966a.tar.gz"
    ) in dockerfile
    assert (
        "sha256:8f1c4cfe1c687918e00bf9ab6f9966ebd4d727d3d64ccb109b2561afcd347b07"
    ) in dockerfile
    for module in (
        "github.com/buger/jsonparser@v1.1.2",
        "golang.org/x/crypto@v0.55.0",
        "golang.org/x/image@v0.45.0",
        "golang.org/x/mod@v0.40.0",
        "golang.org/x/net@v0.57.0",
        "golang.org/x/sync@v0.22.0",
        "golang.org/x/sys@v0.47.0",
        "golang.org/x/term@v0.45.0",
        "golang.org/x/text@v0.41.0",
    ):
        assert module in dockerfile
    assert "go mod verify" in dockerfile
    assert "github.com/ollama/ollama/server.mode=release" in dockerfile
    assert "go version -m /out/ollama" in dockerfile
    assert "generate_go_license.cmake" in dockerfile
    assert "COPY --from=build /out/GO_LICENSE /usr/lib/ollama/GO_LICENSE" in dockerfile
    assert "HOME=/var/lib/ollama" in dockerfile
    assert "USER 10001:10001" in dockerfile

    assert "OLLAMA_IMAGE: careeros-local-ollama:0.33.3-careeros.1" in workflow
    assert "docker compose build backend frontend ollama" in workflow
    assert "Smoke-test patched Ollama runtime" in workflow
    assert "BUILD_PROVENANCE.txt" in workflow
    assert "golang.org/x/crypto[[:space:]]+v0[.]55[.]0" in workflow
    assert "golang.org/x/net[[:space:]]+v0[.]57[.]0" in workflow
    assert "Gate patched Ollama high and critical vulnerabilities" in workflow
    assert "--severity HIGH,CRITICAL" in workflow
    assert "ollama-container.cdx.json" in workflow
    assert "--ignorefile" not in workflow
    assert "check_ollama_vulnerability_policy.py" not in workflow
    assert not (ROOT / ".trivyignore.yaml").exists()
    assert not (ROOT / "scripts/check_ollama_vulnerability_policy.py").exists()


def test_backend_container_smoke_rediscovers_the_ephemeral_port_after_restart() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert workflow.count('published_port="$(docker port "$container_id" 8000/tcp | \\\n') == 2
    assert workflow.count('base_uri="http://127.0.0.1:${published_port}/api/v1"') == 2


def test_notice_gate_verifies_the_approved_payload_portably() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    backend = workflow[workflow.index("  backend:") : workflow.index("  frontend:")]

    assert "python -m scripts.third_party_notices --verify" in backend


def test_container_builds_ship_the_same_canonical_third_party_notices() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    frontend = compose["services"]["frontend"]["build"]
    backend_dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    frontend_dockerfile = (ROOT / "frontend/Dockerfile").read_text(encoding="utf-8")
    ci_workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert frontend == {"context": ".", "dockerfile": "frontend/Dockerfile"}
    assert (
        "COPY scripts/check_node_version.mjs /app/scripts/check_node_version.mjs"
        in frontend_dockerfile
    )
    assert (
        "COPY scripts/validate_frontend_bundle.mjs /app/scripts/validate_frontend_bundle.mjs"
        in frontend_dockerfile
    )
    assert "COPY THIRD_PARTY_NOTICES.txt ./" in backend_dockerfile
    assert "COPY THIRD_PARTY_NOTICES.txt /app/THIRD_PARTY_NOTICES.txt" in frontend_dockerfile
    assert (
        "COPY LICENSE THIRD_PARTY_NOTICES.txt /usr/share/licenses/careeros-local/"
        in backend_dockerfile
    )
    assert (
        "COPY LICENSE THIRD_PARTY_NOTICES.txt /usr/share/licenses/careeros-local/"
        in frontend_dockerfile
    )
    assert "COPY --from=build /app/frontend/dist /usr/share/nginx/html" in frontend_dockerfile
    assert "--chown=nginx:nginx" not in frontend_dockerfile
    assert "RUN chmod -R a-w /usr/share/nginx/html" in frontend_dockerfile
    assert "--no-access-log" in backend_dockerfile
    assert "test ! -w /usr/share/nginx/html/index.html" in ci_workflow
    assert "! grep --fixed-strings '/api/v1/health/ready'" in ci_workflow
    assert '"http://127.0.0.1:${published_port}/THIRD_PARTY_NOTICES.txt"' in ci_workflow
    assert (
        "cmp --silent \\\n"
        "            THIRD_PARTY_NOTICES.txt \\\n"
        '            "$RUNNER_TEMP/careeros-third-party-notices.txt"' in ci_workflow
    )
    assert "Verify backend distribution notices" in ci_workflow
    assert "/app/THIRD_PARTY_NOTICES.txt" in ci_workflow
    assert ci_workflow.count("/usr/share/licenses/careeros-local/") >= 4
