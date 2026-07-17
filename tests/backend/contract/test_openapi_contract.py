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
                    missing.append(
                        f"{source.parent.parent.name}: {method.upper()} {runtime_path}"
                    )

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
