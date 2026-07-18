import re
from pathlib import Path

import pytest

from backend.inference.endpoint import LocalInferenceEndpointError, validate_local_inference_url

PROJECT_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:11434",
        "http://127.0.0.1:11434",
        "http://[::1]:11434",
        "http://ollama:11434",
    ],
)
def test_local_inference_endpoint_accepts_explicit_local_hosts(url):
    assert validate_local_inference_url(url).startswith("http://")


@pytest.mark.parametrize(
    "url",
    [
        "https://inference.example.com/v1",
        "http://192.168.1.50:11434",
        "http://10.0.0.8:11434",
        "http://example.com:11434",
        "ftp://localhost/model",
        "http://user:secret@localhost:11434",
        "http://localhost:11434?token=secret",
    ],
)
def test_local_inference_endpoint_rejects_remote_or_credentialed_urls(url):
    with pytest.raises(LocalInferenceEndpointError):
        validate_local_inference_url(url)


def test_local_inference_endpoint_allows_an_explicit_container_alias():
    assert (
        validate_local_inference_url(
            "http://career-model:11434", allowed_hosts={"career-model"}
        )
        == "http://career-model:11434"
    )


def test_runtime_and_ci_have_no_remote_ai_escape_hatches():
    remote_provider = re.compile(
        r"\b(groq|g4f|deepseek|gemini|openai|anthropic|supabase|sentence-transformers)\b",
        re.IGNORECASE,
    )
    remote_secret = re.compile(r"\b(?:LLM|MODEL|GEMINI|GOOGLE|OPENAI)_(?:API_)?KEY\b")
    build_time_docs = {
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "docs" / "devpost.md",
    }
    build_time_phrases = ("OpenAI Build Week", "OpenAI Codex")
    files = [
        *PROJECT_ROOT.joinpath("backend").rglob("*.py"),
        *PROJECT_ROOT.joinpath("backend").rglob("*.md"),
        *PROJECT_ROOT.joinpath("frontend", "src").rglob("*.js"),
        *PROJECT_ROOT.joinpath("frontend", "src").rglob("*.jsx"),
        *PROJECT_ROOT.joinpath("docs").rglob("*.md"),
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "requirements.txt",
        PROJECT_ROOT / "requirements-dev.txt",
        PROJECT_ROOT / "requirements.lock",
        PROJECT_ROOT / "requirements-dev.lock",
        PROJECT_ROOT / "pyproject.toml",
        PROJECT_ROOT / ".env.example",
        PROJECT_ROOT / "docker-compose.yml",
        PROJECT_ROOT / "frontend" / "package.json",
        PROJECT_ROOT / ".github" / "workflows" / "ci.yml",
    ]
    findings = []
    for path in files:
        if "__pycache__" in path.parts:
            continue
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            providers = {
                match.group(0).lower() for match in remote_provider.finditer(line)
            }
            approved_build_time_reference = (
                path in build_time_docs
                and providers == {"openai"}
                and any(phrase in line for phrase in build_time_phrases)
            )
            if (providers and not approved_build_time_reference) or remote_secret.search(line):
                findings.append(f"{path.relative_to(PROJECT_ROOT)}:{line_number}")
    assert findings == [], "Remote AI boundary violations: " + ", ".join(findings)


def test_compose_hard_disables_ollama_cloud_and_host_exposure():
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    ollama_service = compose.split("  ollama:", maxsplit=1)[1].split(
        "\n  backend:", maxsplit=1
    )[0]

    assert 'OLLAMA_NO_CLOUD: "true"' in ollama_service
    assert "\n    ports:" not in ollama_service
