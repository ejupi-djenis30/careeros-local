import logging
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from backend.core.config import Settings

VALID_TEST_SIGNING_VALUE = "v" * 64


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql://localhost/careeros",
        "sqlite://",
        "sqlite:///file:careeros.db?mode=rw&uri=true",
    ],
)
def test_primary_vault_accepts_only_an_unambiguous_sqlite_url(database_url: str) -> None:
    with pytest.raises(ValueError, match="DATABASE_URL|SQLite"):
        Settings(
            _env_file=None,
            DATABASE_URL=database_url,
            SECRET_KEY=VALID_TEST_SIGNING_VALUE,
        )


def test_production_database_must_be_file_backed_and_inside_data_dir(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    outside = tmp_path / "outside.db"
    with pytest.raises(ValueError, match="file-backed"):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            DATA_DIR=str(data_dir),
            DATABASE_URL="sqlite:///:memory:",
            SECRET_KEY=VALID_TEST_SIGNING_VALUE,
        )
    with pytest.raises(ValueError, match="inside DATA_DIR"):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            DATA_DIR=str(data_dir),
            DATABASE_URL=f"sqlite:///{outside.as_posix()}",
            SECRET_KEY=VALID_TEST_SIGNING_VALUE,
        )

    database = data_dir / "vault" / "careeros.db"
    configured = Settings(
        _env_file=None,
        ENVIRONMENT="production",
        DATA_DIR=str(data_dir),
        DATABASE_URL=f"sqlite:///{database.as_posix()}",
        SECRET_KEY=VALID_TEST_SIGNING_VALUE,
    )
    assert configured.DATABASE_URL.endswith("/vault/careeros.db")


def test_sqlite_busy_timeout_cannot_disable_lock_waiting() -> None:
    with pytest.raises(ValueError, match="SQLITE_BUSY_TIMEOUT_MS"):
        Settings(
            _env_file=None,
            SQLITE_BUSY_TIMEOUT_MS=0,
            SECRET_KEY=VALID_TEST_SIGNING_VALUE,
        )


def test_invalid_development_cors_origins_warn_and_fail_closed(caplog):
    caplog.set_level(logging.WARNING)
    settings = Settings(CORS_ORIGINS="[invalid", SECRET_KEY=VALID_TEST_SIGNING_VALUE)

    assert settings.cors_origins_list == []
    assert "code=runtime_policy_fallback" in caplog.text
    assert "[invalid" not in caplog.text


@pytest.mark.parametrize(
    "origins",
    [
        "*",
        "https://*.example.com",
        "https://user:secret@example.com",
        "https://example.com/private",
        "https://example.com?tenant=one",
        "https://example.com#fragment",
        "https://example.com,https://example.com/",
        "ftp://example.com",
        "tauri://remote",
        "http://remote.example",
        '["https://example.com", 7]',
        "https://example.com,",
    ],
)
def test_invalid_production_cors_origins_abort_startup(origins):
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            SECRET_KEY=VALID_TEST_SIGNING_VALUE,
            CORS_ORIGINS=origins,
        )


def test_cors_origins_are_canonical_and_support_desktop_webviews():
    configured = Settings(
        _env_file=None,
        SECRET_KEY=VALID_TEST_SIGNING_VALUE,
        CORS_ORIGINS=(
            '["HTTPS://Example.COM/",'
            '"http://localhost:5173",'
            '"http://tauri.localhost",'
            '"https://tauri.localhost",'
            '"http://loopback.example:80",'
            '"tauri://LOCALHOST/"]'
        ),
    )

    assert configured.cors_origins_list == [
        "https://example.com",
        "http://localhost:5173",
        "http://tauri.localhost",
        "https://tauri.localhost",
        "http://loopback.example",
        "tauri://localhost",
    ]


def test_default_credentialed_cors_boundary_uses_exact_origins_only():
    configured = Settings(_env_file=None, SECRET_KEY=VALID_TEST_SIGNING_VALUE)

    assert "CORS_ALLOW_ORIGIN_REGEX" not in Settings.model_fields
    assert configured.cors_origins_list == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
    ]


def test_legacy_cors_regex_input_cannot_expand_the_exact_origin_boundary():
    configured = Settings(
        _env_file=None,
        SECRET_KEY=VALID_TEST_SIGNING_VALUE,
        CORS_ALLOW_ORIGIN_REGEX=r"^http://localhost:\d+$",
    )

    assert "CORS_ALLOW_ORIGIN_REGEX" not in type(configured).model_fields
    assert configured.cors_origins_list == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
    ]


@pytest.mark.parametrize(
    "allowed_hosts",
    [
        "[]",
        "[invalid",
        '["*"]',
        '["*.example.com"]',
        '[" localhost"]',
        '["localhost "]',
        '["http://localhost"]',
        '["localhost:8000"]',
        '["localhost/path"]',
        '["localhost","LOCALHOST"]',
        '["bad..host"]',
        '["-bad-host"]',
    ],
)
def test_allowed_hosts_reject_ambiguous_or_noncanonical_input(allowed_hosts):
    with pytest.raises(ValueError, match="ALLOWED_HOSTS"):
        Settings(
            _env_file=None,
            ALLOWED_HOSTS=allowed_hosts,
            SECRET_KEY=VALID_TEST_SIGNING_VALUE,
        )


def test_allowed_hosts_normalize_dns_ip_and_bracketed_ipv6_hosts():
    configured = Settings(
        _env_file=None,
        ALLOWED_HOSTS='["LOCALHOST","127.0.0.1","[::1]","backend"]',
        SECRET_KEY=VALID_TEST_SIGNING_VALUE,
    )

    assert configured.ALLOWED_HOSTS == ["localhost", "127.0.0.1", "::1", "backend"]


@pytest.mark.parametrize("api_prefix", ["/api/v2", "/api/v1/", "api/v1", "", "/"])
def test_api_prefix_is_pinned_to_the_reviewed_private_boundary(api_prefix):
    with pytest.raises(ValueError, match="API_V1_STR"):
        Settings(
            _env_file=None,
            API_V1_STR=api_prefix,
            SECRET_KEY=VALID_TEST_SIGNING_VALUE,
        )


def test_remote_inference_endpoint_is_rejected():
    with pytest.raises(ValueError, match="Local inference"):
        Settings(
            SECRET_KEY=VALID_TEST_SIGNING_VALUE,
            LOCAL_INFERENCE_URL="https://api.example.com/v1",
        )


def test_environment_allowlist_cannot_expand_local_inference_boundary():
    with pytest.raises(ValueError, match="built-in local boundary"):
        Settings(
            SECRET_KEY=VALID_TEST_SIGNING_VALUE,
            LOCAL_INFERENCE_ALLOWED_HOSTS="localhost,remote.example",
            LOCAL_INFERENCE_URL="http://remote.example:11434",
        )


def test_per_step_model_cannot_diverge_from_attested_local_model():
    with pytest.raises(ValueError, match="readiness attests"):
        Settings(
            SECRET_KEY=VALID_TEST_SIGNING_VALUE,
            LOCAL_MODEL="qwen3:1.7b",
            LLM_MATCH_MODEL="another-model",
        )


@pytest.mark.parametrize(
    "field_name",
    [
        "LOCAL_INFERENCE_CONNECT_TIMEOUT_SECONDS",
        "LOCAL_INFERENCE_REQUEST_TIMEOUT_SECONDS",
        "LLM_CALL_TIMEOUT_PLAN",
        "LLM_CALL_TIMEOUT_NORMALIZE",
        "LLM_CALL_TIMEOUT_MATCH",
        "LLM_CALL_TIMEOUT_COACH",
        "LLM_CALL_TIMEOUT_CRITIQUE",
        "LLM_CALL_TIMEOUT_RERANK",
    ],
)
@pytest.mark.parametrize("invalid_value", [0, -1])
def test_inference_timeouts_must_be_strictly_positive(field_name, invalid_value):
    with pytest.raises(ValueError, match=rf"{field_name} must be greater than zero"):
        Settings(
            SECRET_KEY=VALID_TEST_SIGNING_VALUE,
            **{field_name: invalid_value},
        )


@pytest.mark.parametrize(
    "field_name",
    [
        "LOCAL_INFERENCE_CONNECT_TIMEOUT_SECONDS",
        "LOCAL_INFERENCE_REQUEST_TIMEOUT_SECONDS",
        "LLM_CALL_TIMEOUT_PLAN",
        "LLM_CALL_TIMEOUT_NORMALIZE",
        "LLM_CALL_TIMEOUT_MATCH",
        "LLM_CALL_TIMEOUT_COACH",
        "LLM_CALL_TIMEOUT_CRITIQUE",
        "LLM_CALL_TIMEOUT_RERANK",
    ],
)
@pytest.mark.parametrize("invalid_value", [float("nan"), float("inf")])
def test_inference_timeouts_must_be_finite(field_name, invalid_value):
    with pytest.raises(ValueError, match=field_name):
        Settings(
            SECRET_KEY=VALID_TEST_SIGNING_VALUE,
            **{field_name: invalid_value},
        )


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("LLM_TEMPERATURE", -0.1),
        ("LLM_TEMPERATURE", 2.1),
        ("LLM_MATCH_TEMPERATURE", float("nan")),
        ("LLM_TOP_P", -0.1),
        ("LLM_TOP_P", 1.1),
        ("LLM_PLAN_TOP_P", float("inf")),
    ],
)
def test_inference_sampling_policy_must_be_finite_and_bounded(
    field_name,
    invalid_value,
):
    with pytest.raises(ValueError, match=field_name):
        Settings(
            SECRET_KEY=VALID_TEST_SIGNING_VALUE,
            **{field_name: invalid_value},
        )


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("LLM_CONTEXT_WINDOW", 1_023),
        ("LLM_CONTEXT_WINDOW", 1_048_577),
        ("LLM_MAX_TOKENS", 0),
        ("LLM_MAX_TOKENS", 131_073),
        ("LLM_MATCH_CONTEXT_WINDOW", 1_023),
        ("LLM_MATCH_CONTEXT_WINDOW", 1_048_577),
        ("LLM_MATCH_MAX_TOKENS", 0),
    ],
)
def test_inference_context_and_output_budgets_are_bounded(field_name, invalid_value):
    with pytest.raises(ValueError, match="LLM_"):
        Settings(
            SECRET_KEY=VALID_TEST_SIGNING_VALUE,
            **{field_name: invalid_value},
        )


def test_step_output_budget_must_fit_its_context_window():
    with pytest.raises(ValueError, match="LLM_MATCH_MAX_TOKENS"):
        Settings(
            SECRET_KEY=VALID_TEST_SIGNING_VALUE,
            LLM_MATCH_CONTEXT_WINDOW=2_048,
            LLM_MATCH_MAX_TOKENS=2_049,
        )


@pytest.mark.parametrize("model", ["", "x" * 257, "model\nforged"])
def test_local_model_identifier_is_safe_at_startup(model):
    with pytest.raises(ValueError, match="LOCAL_MODEL"):
        Settings(
            SECRET_KEY=VALID_TEST_SIGNING_VALUE,
            LOCAL_MODEL=model,
        )


@pytest.mark.parametrize(
    "field_name",
    [
        "MAX_UPLOAD_FILE_SIZE",
        "HTTP_REQUEST_BODY_MAX_BYTES",
        "PORTABLE_ARCHIVE_REQUEST_BODY_MAX_BYTES",
        "CV_IMPORT_MAX_PAGES",
        "CV_IMPORT_MAX_EXTRACTED_CHARS",
        "SOURCE_IMPORT_MAX_PAGES",
        "SOURCE_IMPORT_MAX_EXTRACTED_CHARS",
        "SOURCE_IMPORT_MAX_ARCHIVE_MEMBERS",
        "SOURCE_IMPORT_MAX_UNCOMPRESSED_BYTES",
        "RESUME_MAX_PAGES",
        "RESUME_PHOTO_MAX_PIXELS",
        "RESUME_PHOTO_EDGE_PX",
        "PORTABLE_ARCHIVE_MAX_BYTES",
        "PORTABLE_ARCHIVE_MAX_UNCOMPRESSED_BYTES",
        "PORTABLE_ARCHIVE_MAX_MEMBERS",
        "PORTABLE_ARCHIVE_MAX_RECORDS",
    ],
)
def test_local_resource_limits_must_be_positive(field_name):
    with pytest.raises(ValueError, match=field_name):
        Settings(
            SECRET_KEY=VALID_TEST_SIGNING_VALUE,
            **{field_name: 0},
        )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("MAX_UPLOAD_FILE_SIZE", 64 * 1024 * 1024 + 1),
        ("HTTP_REQUEST_BODY_MAX_BYTES", 128 * 1024 * 1024 + 1),
        ("PORTABLE_ARCHIVE_REQUEST_BODY_MAX_BYTES", 640 * 1024 * 1024 + 1),
        ("CV_IMPORT_MAX_PAGES", 1_001),
        ("CV_IMPORT_MAX_EXTRACTED_CHARS", 5_000_001),
        ("SOURCE_IMPORT_MAX_PAGES", 2_001),
        ("SOURCE_IMPORT_MAX_EXTRACTED_CHARS", 10_000_001),
        ("SOURCE_IMPORT_MAX_ARCHIVE_MEMBERS", 10_001),
        ("SOURCE_IMPORT_MAX_UNCOMPRESSED_BYTES", 256 * 1024 * 1024 + 1),
        ("RESUME_MAX_PAGES", 21),
        ("RESUME_PHOTO_MAX_PIXELS", 100_000_001),
        ("RESUME_PHOTO_EDGE_PX", 4_097),
        ("PORTABLE_ARCHIVE_MAX_BYTES", 512 * 1024 * 1024 + 1),
        ("PORTABLE_ARCHIVE_MAX_UNCOMPRESSED_BYTES", 1024 * 1024 * 1024 + 1),
        ("PORTABLE_ARCHIVE_MAX_MEMBERS", 20_001),
        ("PORTABLE_ARCHIVE_MAX_RECORDS", 1_000_001),
    ],
)
def test_local_resource_limits_have_hard_configuration_ceilings(field_name, value):
    with pytest.raises(ValueError, match=field_name):
        Settings(
            SECRET_KEY=VALID_TEST_SIGNING_VALUE,
            **{field_name: value},
        )


def test_docx_expansion_budget_must_cover_the_upload_budget():
    with pytest.raises(ValueError, match="SOURCE_IMPORT_MAX_UNCOMPRESSED_BYTES"):
        Settings(
            SECRET_KEY=VALID_TEST_SIGNING_VALUE,
            MAX_UPLOAD_FILE_SIZE=1_024,
            SOURCE_IMPORT_MAX_UNCOMPRESSED_BYTES=1_023,
        )


def test_http_body_budget_must_leave_room_for_multipart_framing():
    with pytest.raises(ValueError, match="HTTP_REQUEST_BODY_MAX_BYTES"):
        Settings(
            SECRET_KEY=VALID_TEST_SIGNING_VALUE,
            MAX_UPLOAD_FILE_SIZE=1_024,
            HTTP_REQUEST_BODY_MAX_BYTES=1_024,
        )


def test_portable_http_body_budget_must_leave_room_for_archive_framing():
    with pytest.raises(ValueError, match="PORTABLE_ARCHIVE_REQUEST_BODY_MAX_BYTES"):
        Settings(
            SECRET_KEY=VALID_TEST_SIGNING_VALUE,
            PORTABLE_ARCHIVE_MAX_BYTES=2_048,
            PORTABLE_ARCHIVE_REQUEST_BODY_MAX_BYTES=2_048,
        )


def test_normalized_photo_dimensions_must_fit_the_pixel_budget():
    with pytest.raises(ValueError, match="RESUME_PHOTO_EDGE_PX"):
        Settings(
            SECRET_KEY=VALID_TEST_SIGNING_VALUE,
            RESUME_PHOTO_EDGE_PX=2_000,
            RESUME_PHOTO_MAX_PIXELS=3_000_000,
        )


def test_portable_expansion_budget_must_cover_the_archive_budget():
    with pytest.raises(ValueError, match="PORTABLE_ARCHIVE_MAX_UNCOMPRESSED_BYTES"):
        Settings(
            SECRET_KEY=VALID_TEST_SIGNING_VALUE,
            PORTABLE_ARCHIVE_MAX_BYTES=2_048,
            PORTABLE_ARCHIVE_MAX_UNCOMPRESSED_BYTES=1_024,
        )


def test_production_rejects_development_signing_value():
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(ENVIRONMENT="production", SECRET_KEY="local-development-only")


@pytest.mark.parametrize(
    "environment",
    ["prodution", "Production", " production ", "staging", ""],
)
def test_environment_must_be_an_exact_supported_value(environment):
    with pytest.raises(ValueError, match="ENVIRONMENT"):
        Settings(
            _env_file=None,
            ENVIRONMENT=environment,
            SECRET_KEY=VALID_TEST_SIGNING_VALUE,
        )


@pytest.mark.parametrize(
    "secret",
    [
        "",
        "short",
        "x" * 31,
        f" {'x' * 32}",
        f"{'x' * 32} ",
        f"{'x' * 16}\n{'y' * 16}",
        f"{'x' * 16}\u007f{'y' * 16}",
    ],
)
def test_production_signing_secret_has_a_strict_length_and_character_floor(secret):
    with pytest.raises(ValueError, match="at least 32 characters"):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            SECRET_KEY=secret,
        )


@pytest.mark.parametrize("algorithm", ["HS384", "HS512", "RS256", "hs256", ""])
def test_jwt_algorithm_is_pinned_to_the_reviewed_value(algorithm):
    with pytest.raises(ValueError, match="ALGORITHM"):
        Settings(
            _env_file=None,
            ALGORITHM=algorithm,
            SECRET_KEY=VALID_TEST_SIGNING_VALUE,
        )


def test_production_loads_persisted_installation_signing_value(monkeypatch):
    persisted_value = "p" * 64
    with TemporaryDirectory() as directory:
        data_dir = Path(directory)
        fixture_path = data_dir / "installation-value.fixture"
        fixture_path.write_text(persisted_value, encoding="utf-8")
        monkeypatch.delenv("SECRET_KEY", raising=False)
        monkeypatch.setenv("DATA_DIR", str(data_dir))
        monkeypatch.setenv("CAREEROS_SECRET_FILE", str(fixture_path))

        loaded = Settings(
            _env_file=None,
            ENVIRONMENT="production",
            DATABASE_URL=f"sqlite:///{(data_dir / 'careeros.db').as_posix()}",
        )

        assert loaded.SECRET_KEY == persisted_value


def test_production_fallback_rejects_a_linked_installation_signing_value(
    monkeypatch,
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    target = tmp_path / "external-secret"
    target.write_text("s" * 64, encoding="ascii")
    secret = data_dir / ".secret-key"
    try:
        secret.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"File symlinks are unavailable: {exc}")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("CAREEROS_SECRET_FILE", str(secret))

    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            DATABASE_URL=f"sqlite:///{(data_dir / 'careeros.db').as_posix()}",
        )

    assert target.read_text(encoding="ascii") == "s" * 64
