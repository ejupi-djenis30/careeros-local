"""Compatible provider configuration service composed from focused domain slices."""

from .catalog import (
    MAX_PROVIDERS_PER_USER as MAX_PROVIDERS_PER_USER,
)
from .catalog import (
    ProviderConfigurationError as ProviderConfigurationError,
)
from .catalog import (
    _provider_origin as _provider_origin,
)
from .catalog import (
    _redacted_request as _redacted_request,
)
from .catalog import (
    _validate_declaration as _validate_declaration,
)
from .catalog import (
    configuration_view as configuration_view,
)
from .catalog import (
    materialize_configuration as materialize_configuration,
)
from .imports import MAX_IMPORT_DOCUMENT_BYTES as MAX_IMPORT_DOCUMENT_BYTES
from .imports import ProviderImports
from .mutations import ProviderMutations


class ProviderConfigurationService(ProviderMutations, ProviderImports):
    """Keep the established CRUD/import API and transaction boundaries unchanged."""
