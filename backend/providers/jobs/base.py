from abc import ABC, abstractmethod

from backend.providers.jobs.models import JobSearchRequest, ProviderInfo


class JobProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """The unique identifier name of the provider."""
        pass

    @property
    def throttle_delay(self) -> float:
        """Delay in seconds to pause between paginated requests for this provider.
        Override in subclasses that require rate-limit throttling (e.g. Adecco)."""
        return 0.0

    @abstractmethod
    def get_provider_info(self) -> ProviderInfo:
        """Get the provider's capabilities and description for the LLM."""
        pass

    @abstractmethod
    async def search(self, request: JobSearchRequest) -> "JobSearchResponse":  # noqa: F821
        """Search for jobs."""
        pass
