"""MCP registration for the same provider lifecycle exposed by the desktop."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from backend.automation.mcp_annotations import DESTRUCTIVE, MUTATION, NETWORK_READ, READ_ONLY
from backend.automation.mcp_invocation import AsyncInvoker, SyncInvoker
from backend.providers.configuration.schemas import (
    ProviderConfigurationCreate,
    ProviderConfigurationUpdate,
    ProviderConfigurationView,
    ProviderImportRequest,
    ProviderImportResultView,
    ProviderPackInstallRequest,
    ProviderPackSummaryView,
    ProviderStateUpdate,
    ProviderTestRequest,
    ProviderTestView,
    ProviderValidationView,
)

if TYPE_CHECKING:
    from backend.automation.facade import AutomationFacade


def register_provider_tools(
    server: FastMCP,
    facade: AutomationFacade,
    invoke: SyncInvoker,
    invoke_async: AsyncInvoker,
) -> None:
    if facade.allows("providers:read"):

        async def list_provider_configurations() -> list[ProviderConfigurationView]:
            """List every installed provider with stored credential values redacted."""

            return await invoke(facade.list_provider_configurations)

        async def list_provider_packs() -> list[ProviderPackSummaryView]:
            """List bundled provider packs without installing or enabling any provider."""

            return await invoke(facade.list_provider_packs)

        server.add_tool(
            list_provider_configurations,
            name="list_provider_configurations",
            annotations=READ_ONLY,
        )
        server.add_tool(list_provider_packs, name="list_provider_packs", annotations=READ_ONLY)

    if facade.allows("providers:write"):

        async def validate_provider_configuration(
            configuration: ProviderConfigurationCreate,
        ) -> ProviderValidationView:
            """Validate a declarative provider without making a network request."""

            return await invoke(facade.validate_provider_configuration, configuration)

        async def create_provider_configuration(
            configuration: ProviderConfigurationCreate,
        ) -> ProviderConfigurationView:
            """Create a revisioned JSON or HTML provider declaration."""

            return await invoke(facade.create_provider_configuration, configuration)

        async def import_provider_document(
            provider_import: ProviderImportRequest,
        ) -> ProviderImportResultView:
            """Atomically import one strict provider document or provider pack."""

            return await invoke(facade.import_provider_document, provider_import)

        async def import_bundled_provider_pack(
            pack_id: Annotated[str, Field(min_length=3, max_length=160)],
            install: ProviderPackInstallRequest,
        ) -> ProviderImportResultView:
            """Explicitly import a discoverable bundled pack; activation is an explicit option."""

            return await invoke(facade.import_bundled_provider_pack, pack_id, install)

        async def set_provider_state(
            configuration_id: Annotated[str, Field(min_length=36, max_length=36)],
            state: ProviderStateUpdate,
        ) -> ProviderConfigurationView:
            """Enable or disable an owned provider at its expected revision."""

            return await invoke(facade.set_provider_state, configuration_id, state)

        async def update_provider_configuration(
            configuration_id: Annotated[str, Field(min_length=36, max_length=36)],
            configuration: ProviderConfigurationUpdate,
        ) -> ProviderConfigurationView:
            """Update an owned provider with an expected revision."""

            return await invoke(
                facade.update_provider_configuration,
                configuration_id,
                configuration,
            )

        async def delete_provider_configuration(
            configuration_id: Annotated[str, Field(min_length=36, max_length=36)],
            expected_revision: Annotated[int, Field(ge=1)],
        ) -> dict[str, bool]:
            """Delete an installed provider at the expected revision."""

            return await invoke(
                facade.delete_provider_configuration,
                configuration_id,
                expected_revision=expected_revision,
            )

        server.add_tool(
            validate_provider_configuration,
            name="validate_provider_configuration",
            annotations=READ_ONLY,
        )
        server.add_tool(
            create_provider_configuration,
            name="create_provider_configuration",
            annotations=MUTATION,
        )
        server.add_tool(
            import_provider_document,
            name="import_provider_document",
            annotations=MUTATION,
        )
        server.add_tool(
            import_bundled_provider_pack,
            name="import_bundled_provider_pack",
            annotations=MUTATION,
        )
        server.add_tool(set_provider_state, name="set_provider_state", annotations=MUTATION)
        server.add_tool(
            update_provider_configuration,
            name="update_provider_configuration",
            annotations=MUTATION,
        )
        server.add_tool(
            delete_provider_configuration,
            name="delete_provider_configuration",
            annotations=DESTRUCTIVE,
        )

    if facade.allows("providers:write") and facade.allows("search:execute"):

        async def test_provider_configuration(
            configuration_id: Annotated[str, Field(min_length=36, max_length=36)],
            test: ProviderTestRequest,
        ) -> ProviderTestView:
            """Perform one bounded public-network request and return a redacted sample."""

            return await invoke_async(
                facade.test_provider_configuration,
                configuration_id,
                test,
            )

        server.add_tool(
            test_provider_configuration,
            name="test_provider_configuration",
            annotations=NETWORK_READ,
        )
