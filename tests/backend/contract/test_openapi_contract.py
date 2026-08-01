from pathlib import Path

import yaml

from backend.core.config import settings
from backend.main import app

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATHS = sorted(PROJECT_ROOT.glob("specs/*/contracts/openapi.yaml"))
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def test_spec_kit_openapi_operations_exist_in_runtime_schema():
    runtime_paths = app.openapi()["paths"]
    missing: list[str] = []

    assert CONTRACT_PATHS, "No Spec Kit OpenAPI contracts were discovered"
    for source in CONTRACT_PATHS:
        contract = yaml.safe_load(source.read_text(encoding="utf-8"))
        for contract_path, path_item in contract["paths"].items():
            runtime_path = f"{settings.API_V1_STR}{contract_path}"
            if runtime_path not in runtime_paths:
                missing.append(f"{source.parent.parent.name}: {runtime_path}")
                continue
            for method in HTTP_METHODS & set(path_item):
                if method not in runtime_paths[runtime_path]:
                    missing.append(f"{source.parent.parent.name}: {method.upper()} {runtime_path}")

    assert missing == [], "Contract operations missing from runtime OpenAPI: " + ", ".join(missing)


def test_spec_kit_contract_has_unique_operation_ids_and_no_remote_ai_surface():
    operation_ids: list[str] = []
    serialized = ""
    for source in CONTRACT_PATHS:
        text = source.read_text(encoding="utf-8")
        contract = yaml.safe_load(text)
        operation_ids.extend(
            operation["operationId"]
            for path_item in contract["paths"].values()
            for method, operation in path_item.items()
            if method in HTTP_METHODS
        )
        serialized += text.casefold()

    assert len(operation_ids) == len(set(operation_ids))
    assert all(name not in serialized for name in ("openai", "gemini", "anthropic", "groq"))


def test_portable_archive_inspection_contract_matches_runtime_schema():
    runtime = app.openapi()
    static = yaml.safe_load(
        (
            PROJECT_ROOT / "specs" / "001-desktop-career-agent" / "contracts" / "openapi.yaml"
        ).read_text(encoding="utf-8")
    )
    runtime_operation = runtime["paths"][f"{settings.API_V1_STR}/portability/inspect"]["post"]
    static_operation = static["paths"]["/portability/inspect"]["post"]
    runtime_schema = runtime["components"]["schemas"]["ArchiveInspection"]
    static_schema = static["components"]["schemas"]["ArchiveInspection"]

    assert runtime_operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ArchiveInspection"
    }
    assert static_operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ArchiveInspection"
    }
    expected_too_large_variants = [
        {"$ref": "#/components/schemas/PrivateErrorResponse"},
        {"$ref": "#/components/schemas/MaintenanceErrorResponse"},
    ]
    for path in ("/portability/inspect", "/portability/restore"):
        assert (
            static["paths"][path]["post"]["responses"]["413"]["content"]["application/json"][
                "schema"
            ]["oneOf"]
            == expected_too_large_variants
        )
    assert set(runtime_schema["required"]) == set(static_schema["required"])
    assert (
        static_operation["requestBody"]["content"]["multipart/form-data"]["schema"]["properties"][
            "file"
        ]["maxLength"]
        == settings.PORTABLE_ARCHIVE_MAX_BYTES
    )
    for field in ("verification_codes", "warning_codes"):
        assert (
            runtime_schema["properties"][field]["items"]["enum"]
            == static_schema["properties"][field]["items"]["enum"]
        )


def test_agent_access_runtime_and_static_contract_document_both_auth_boundaries():
    runtime = app.openapi()
    static = yaml.safe_load(
        (
            PROJECT_ROOT / "specs" / "001-desktop-career-agent" / "contracts" / "openapi.yaml"
        ).read_text(encoding="utf-8")
    )
    operations = (
        ("/automation/grants", "get"),
        ("/automation/grants", "post"),
        ("/automation/grants/{grant_id}/revoke", "post"),
    )

    assert runtime["components"]["securitySchemes"]["desktopSession"] == {
        "type": "apiKey",
        "description": (
            "Per-launch native-shell secret. The middleware enforces it in desktop mode; "
            "explicit browser development disables that boundary."
        ),
        "in": "header",
        "name": "X-CareerOS-Session",
    }
    for path, method in operations:
        runtime_operation = runtime["paths"][f"{settings.API_V1_STR}{path}"][method]
        static_operation = static["paths"][path][method]
        assert runtime_operation["security"] == [{"desktopSession": [], "OAuth2PasswordBearer": []}]
        assert static_operation["security"] == [{"desktopSession": [], "userAccessToken": []}]
        assert "403" in runtime_operation["responses"]
        assert "403" in static_operation["responses"]

    for path, method in operations[1:]:
        runtime_schema = runtime["paths"][f"{settings.API_V1_STR}{path}"][method]["responses"][
            "403"
        ]["content"]["application/json"]["schema"]
        static_schema = static["paths"][path][method]["responses"]["403"]["content"][
            "application/json"
        ]["schema"]
        assert len(runtime_schema["anyOf"]) == 2
        assert len(static_schema["oneOf"]) == 2


def test_agent_access_runtime_and_static_schemas_share_secret_and_bound_contracts():
    runtime = app.openapi()
    static = yaml.safe_load(
        (
            PROJECT_ROOT / "specs" / "001-desktop-career-agent" / "contracts" / "openapi.yaml"
        ).read_text(encoding="utf-8")
    )
    runtime_schemas = runtime["components"]["schemas"]
    static_schemas = static["components"]["schemas"]
    expected_scopes = [
        "system:read",
        "career:read",
        "resume:read",
        "applications:read",
    ]

    runtime_issue = runtime_schemas["GrantIssueRequest"]
    static_issue = static_schemas["AutomationGrantIssue"]
    assert set(runtime_issue["required"]) == set(static_issue["required"])
    assert runtime_issue["additionalProperties"] is static_issue["additionalProperties"] is False
    for field in ("label", "scopes", "lifetime_days", "password"):
        runtime_field = runtime_issue["properties"][field]
        static_field = static_issue["properties"][field]
        for bound in (
            "minLength",
            "maxLength",
            "minItems",
            "maxItems",
            "minimum",
            "maximum",
            "default",
            "format",
            "writeOnly",
        ):
            assert runtime_field.get(bound) == static_field.get(bound)
    assert runtime_issue["properties"]["scopes"]["items"]["enum"] == expected_scopes
    assert (
        static_issue["properties"]["scopes"]["items"]["$ref"]
        == "#/components/schemas/AutomationScope"
    )
    assert static_schemas["AutomationScope"]["enum"] == expected_scopes

    runtime_grant = runtime_schemas["GrantView"]
    static_grant = static_schemas["AutomationGrant"]
    assert set(runtime_grant["required"]) == set(static_grant["required"])
    for field in ("id", "label", "scopes", "expires_at", "created_at"):
        for contract_key in (
            "format",
            "minLength",
            "maxLength",
            "minItems",
            "maxItems",
            "uniqueItems",
        ):
            assert runtime_grant["properties"][field].get(contract_key) == (
                static_grant["properties"][field].get(contract_key)
            )
    assert "token" not in runtime_grant["properties"]
    assert "token_digest" not in runtime_grant["properties"]
    assert "user_id" not in runtime_grant["properties"]

    runtime_issued = runtime_schemas["GrantIssuedView"]
    static_issued = static_schemas["AutomationGrantIssued"]
    assert set(runtime_issued["required"]) == set(static_issued["required"])
    for contract_key in ("minLength", "maxLength", "readOnly"):
        assert (
            runtime_issued["properties"]["token"][contract_key]
            == (static_issued["properties"]["token"][contract_key])
        )
    assert (
        runtime_issued["properties"]["token_environment_variable"]["const"]
        == (static_issued["properties"]["token_environment_variable"]["const"])
    )
    assert (
        runtime_issued["properties"]["warning"]["const"]
        == (static_issued["properties"]["warning"]["const"])
    )
