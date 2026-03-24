from abc import ABC, abstractmethod
from typing import List
from backend.providers.jobs.models import JobListing, JobSearchRequest, ProviderInfo

class JobProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """The unique identifier name of the provider."""
        pass

    @abstractmethod
    def get_provider_info(self) -> ProviderInfo:
        """Get the provider's capabilities and description for the LLM."""
        pass

    @abstractmethod
    async def search(self, request: JobSearchRequest) -> "JobSearchResponse":
        """Search for jobs."""
        pass

