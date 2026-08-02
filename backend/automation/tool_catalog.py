"""Single capability map shared by status reporting and MCP registration tests."""

from __future__ import annotations

from backend.automation.schemas import AutomationScope

TOOL_SCOPES: dict[str, frozenset[AutomationScope]] = {
    "get_status": frozenset({"system:read"}),
    "get_local_model_status": frozenset({"system:read"}),
    "get_career_summary": frozenset({"career:read"}),
    "get_career_profile": frozenset({"career:read"}),
    "save_career_profile": frozenset({"career:write"}),
    "get_resume_catalog": frozenset({"resume:read"}),
    "get_resume": frozenset({"resume:read"}),
    "generate_resume": frozenset({"resume:write"}),
    "update_resume": frozenset({"resume:write"}),
    "publish_resume": frozenset({"resume:write"}),
    "list_jobs": frozenset({"jobs:read"}),
    "get_job": frozenset({"jobs:read"}),
    "create_job": frozenset({"jobs:write"}),
    "update_job": frozenset({"jobs:write"}),
    "record_job_view": frozenset({"jobs:write"}),
    "dismiss_job": frozenset({"jobs:write"}),
    "delete_job": frozenset({"jobs:write"}),
    "run_job_search": frozenset({"search:execute", "jobs:read"}),
    "list_provider_configurations": frozenset({"providers:read"}),
    "list_provider_packs": frozenset({"providers:read"}),
    "validate_provider_configuration": frozenset({"providers:write"}),
    "create_provider_configuration": frozenset({"providers:write"}),
    "import_provider_document": frozenset({"providers:write"}),
    "import_bundled_provider_pack": frozenset({"providers:write"}),
    "set_provider_state": frozenset({"providers:write"}),
    "update_provider_configuration": frozenset({"providers:write"}),
    "delete_provider_configuration": frozenset({"providers:write"}),
    "test_provider_configuration": frozenset({"providers:write", "search:execute"}),
    "list_applications": frozenset({"applications:read"}),
    "get_application": frozenset({"applications:read"}),
    "get_application_readiness": frozenset({"applications:read"}),
    "get_application_agenda": frozenset({"applications:read"}),
    "get_application_dossier_draft": frozenset({"applications:read"}),
    "create_application": frozenset({"applications:write"}),
    "append_application_event": frozenset({"applications:write"}),
    "update_application_preparation": frozenset({"applications:write"}),
    "create_application_task": frozenset({"applications:write"}),
    "update_application_task": frozenset({"applications:write"}),
    "put_application_dossier_draft": frozenset({"applications:write"}),
    "delete_application_dossier_draft": frozenset({"applications:write"}),
    "publish_application_dossier": frozenset({"applications:write"}),
}


def available_tool_names(scopes: frozenset[AutomationScope]) -> list[str]:
    return [name for name, required in TOOL_SCOPES.items() if required.issubset(scopes)]
