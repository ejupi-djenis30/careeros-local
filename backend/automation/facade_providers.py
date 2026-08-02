"""Provider operations for a scoped automation principal."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from backend.providers.configuration.network_policy import UnsafeProviderDestination
from backend.providers.configuration.packs import (
    ProviderPackError,
    bundled_provider_pack,
    bundled_provider_pack_summaries,
)
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
from backend.providers.configuration.service import (
    ProviderConfigurationError,
    ProviderConfigurationService,
)
from backend.providers.configuration.tester import test_provider_configuration
from backend.providers.jobs.exceptions import ProviderError

if TYPE_CHECKING:
    from backend.automation.grants import AutomationPrincipal
    from backend.automation.schemas import AutomationScope


class ProviderOperationsMixin:
    if TYPE_CHECKING:
        _session_factory: Any
        principal: AutomationPrincipal

        def _require(self, scope: AutomationScope) -> None: ...

    def list_provider_configurations(self) -> list[ProviderConfigurationView]:
        self._require("providers:read")
        with self._session_factory() as db:
            return ProviderConfigurationService(db).list(self.principal.user_id)

    def list_provider_packs(self) -> list[ProviderPackSummaryView]:
        self._require("providers:read")
        try:
            return bundled_provider_pack_summaries()
        except ProviderPackError as exc:
            from backend.automation.facade import AutomationFacadeError

            raise AutomationFacadeError(
                "provider_packs_unavailable", "Bundled provider packs are unavailable"
            ) from exc

    def import_provider_document(
        self, payload: ProviderImportRequest
    ) -> ProviderImportResultView:
        self._require("providers:write")
        try:
            with self._session_factory() as db:
                return ProviderConfigurationService(db).import_document(
                    self.principal.user_id,
                    payload.document,
                    activate=payload.activate,
                )
        except (ProviderConfigurationError, UnsafeProviderDestination, ValueError) as exc:
            from backend.automation.facade import AutomationFacadeError

            code = exc.code if isinstance(exc, ProviderConfigurationError) else "invalid_provider_import"
            raise AutomationFacadeError(code, str(exc)) from exc

    def import_bundled_provider_pack(
        self, pack_id: str, payload: ProviderPackInstallRequest
    ) -> ProviderImportResultView:
        self._require("providers:write")
        try:
            pack = bundled_provider_pack(pack_id)
            with self._session_factory() as db:
                return ProviderConfigurationService(db).import_document(
                    self.principal.user_id,
                    pack,
                    activate=payload.activate,
                )
        except ProviderPackError as exc:
            from backend.automation.facade import AutomationFacadeError

            raise AutomationFacadeError("provider_pack_not_found", str(exc)) from exc
        except (ProviderConfigurationError, UnsafeProviderDestination, ValueError) as exc:
            from backend.automation.facade import AutomationFacadeError

            code = exc.code if isinstance(exc, ProviderConfigurationError) else "invalid_provider_import"
            raise AutomationFacadeError(code, str(exc)) from exc

    def set_provider_state(
        self,
        configuration_id: str,
        payload: ProviderStateUpdate,
    ) -> ProviderConfigurationView:
        self._require("providers:write")
        try:
            with self._session_factory() as db:
                return ProviderConfigurationService(db).set_enabled(
                    self.principal.user_id,
                    configuration_id,
                    payload,
                )
        except ProviderConfigurationError as exc:
            from backend.automation.facade import AutomationFacadeError

            raise AutomationFacadeError(exc.code, str(exc)) from exc

    def validate_provider_configuration(
        self, payload: ProviderConfigurationCreate
    ) -> ProviderValidationView:
        self._require("providers:write")
        try:
            with self._session_factory() as db:
                return ProviderConfigurationService(db).validate(payload)
        except (ProviderConfigurationError, UnsafeProviderDestination, ValueError) as exc:
            from backend.automation.facade import AutomationFacadeError

            raise AutomationFacadeError(
                "invalid_provider_configuration", "Provider configuration is invalid"
            ) from exc

    def create_provider_configuration(
        self, payload: ProviderConfigurationCreate
    ) -> ProviderConfigurationView:
        self._require("providers:write")
        try:
            with self._session_factory() as db:
                return ProviderConfigurationService(db).create(self.principal.user_id, payload)
        except (ProviderConfigurationError, UnsafeProviderDestination, ValueError) as exc:
            from backend.automation.facade import AutomationFacadeError

            code = (
                exc.code
                if isinstance(exc, ProviderConfigurationError)
                else "invalid_provider_configuration"
            )
            raise AutomationFacadeError(code, str(exc)) from exc

    def update_provider_configuration(
        self,
        configuration_id: str,
        payload: ProviderConfigurationUpdate,
    ) -> ProviderConfigurationView:
        self._require("providers:write")
        try:
            with self._session_factory() as db:
                return ProviderConfigurationService(db).update(
                    self.principal.user_id, configuration_id, payload
                )
        except (ProviderConfigurationError, UnsafeProviderDestination, ValueError) as exc:
            from backend.automation.facade import AutomationFacadeError

            code = (
                exc.code
                if isinstance(exc, ProviderConfigurationError)
                else "invalid_provider_configuration"
            )
            raise AutomationFacadeError(code, str(exc)) from exc

    def delete_provider_configuration(
        self, configuration_id: str, *, expected_revision: int
    ) -> dict[str, bool]:
        self._require("providers:write")
        try:
            with self._session_factory() as db:
                ProviderConfigurationService(db).delete(
                    self.principal.user_id,
                    configuration_id,
                    expected_revision=expected_revision,
                )
        except ProviderConfigurationError as exc:
            from backend.automation.facade import AutomationFacadeError

            raise AutomationFacadeError(exc.code, str(exc)) from exc
        return {"deleted": True}

    async def test_provider_configuration(
        self,
        configuration_id: str,
        payload: ProviderTestRequest,
    ) -> ProviderTestView:
        self._require("providers:write")
        self._require("search:execute")
        try:
            with self._session_factory() as db:
                return await test_provider_configuration(
                    db,
                    user_id=self.principal.user_id,
                    configuration_id=configuration_id,
                    request=payload,
                )
        except ProviderConfigurationError as exc:
            from backend.automation.facade import AutomationFacadeError

            raise AutomationFacadeError(exc.code, str(exc)) from exc
        except (ProviderError, UnsafeProviderDestination) as exc:
            from backend.automation.facade import AutomationFacadeError

            raise AutomationFacadeError(
                "provider_test_failed", "Provider test failed safely"
            ) from exc
