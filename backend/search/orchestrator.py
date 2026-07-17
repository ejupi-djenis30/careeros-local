# ruff: noqa: E402, F401, I001

import asyncio
import inspect
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.jobs.matching import deterministic_job_match
from backend.models import ScrapedJob, SearchProfile
from backend.providers.circuit_breaker import CircuitOpenError
from backend.providers.jobs.jobroom.client import JobRoomProvider
from backend.providers.jobs.swissdevjobs.client import SwissDevJobsProvider
from backend.repositories.job_repository import JobRepository
from backend.repositories.profile_repository import ProfileRepository
from backend.services.llm_service import llm_service
from backend.search.normalization.listings import (
    bootstrap_normalized_job_data,
    coerce_int,
    coerce_string_list,
    extract_company_name,
    extract_listing_description_text,
    extract_listing_location_string,
    extract_listing_workload_string,
    extract_salary_max_chf,
    listing_description_fingerprint,
    listing_fuzzy_key,
    listing_identity_key,
    listing_is_remote,
    listing_url_token,
    normalize_listing_identifier,
    parse_listing_publication_date,
)
from backend.services.search.matching_engine import SearchNormalizationFilterEngine
from backend.services.search.persistence import SearchPipelinePersistence
from backend.services.search.prompt_compaction import (
    build_profile_match_snapshot,
    build_profile_normalization_fingerprint,
)
from backend.services.search.search_validator import build_search_request
from backend.services.utils import (
    geocode_location,
    haversine_distance,
)

try:
    from backend.providers.jobs.adecco.client import AdeccoProvider
except ImportError:
    AdeccoProvider = None
from backend.providers.jobs.jobroom.avam_mapper import avam_mapper
from backend.providers.jobs.localdb.client import LocalDbProvider
from backend.providers.jobs.models import (
    JobSearchRequest,
)
from backend.services.search.profile_preferences import get_profile_preference
from backend.services.search.query_contracts import (
    build_plan_cache_payload,
    compute_plan_input_fingerprint,
    exact_query_fingerprint,
    is_cached_plan_compatible,
    normalize_domain,
    normalize_language,
    normalize_search_item,
    route_provider_names,
    supported_request_language,
    unpack_plan_cache_payload,
)
from backend.services.search_status import (
    add_log,
    get_status,
    init_status,
    register_task,
    release_task,
    unregister_task,
    update_status,
)

logger = logging.getLogger(__name__)


STOP_STATES = {"stopped", "cancelled", "finished", "failed"}


# ─────────────────────── Domain Router ───────────────────────


def get_compatible_providers(
    query_domain: str,
    providers: Dict[str, Any],
    provider_infos: Dict[str, Any],
) -> List[str]:
    return route_provider_names({"domain": query_domain}, providers, provider_infos)

import sys
import types

from backend.search import (
    acquisition,
    finalization,
    matching,
    normalization_pipeline,
    persistence,
)
from backend.search.acquisition import AcquisitionMixin
from backend.search.persistence import PersistenceMixin
from backend.search.normalization_pipeline import NormalizationMixin
from backend.search.matching import MatchingMixin
from backend.search.finalization import FinalizationMixin


class SearchService(AcquisitionMixin, PersistenceMixin, NormalizationMixin, MatchingMixin, FinalizationMixin):
    """Composition root for local acquisition, normalization, matching and persistence."""

    def __init__(
        self,
        db: Session = None,
        job_repo=None,
        profile_repo=None,
        normalization_filter_engine: SearchNormalizationFilterEngine | None = None,
        search_persistence: SearchPipelinePersistence | None = None,
    ):
        self.db = db or getattr(job_repo, "db", None) or getattr(profile_repo, "db", None)
        self.job_repo = job_repo or (JobRepository(db) if db else None)
        self.profile_repo = profile_repo or (ProfileRepository(db) if db else None)
        self.normalization_filter_engine = (
            normalization_filter_engine or SearchNormalizationFilterEngine()
        )
        self.search_persistence = search_persistence or SearchPipelinePersistence(
            self.db,
            self.job_repo,
        )
        # Providers (registered by domain)
        self.providers = {
            "job_room": JobRoomProvider(),
            "swissdevjobs": SwissDevJobsProvider(),
            "local_db": LocalDbProvider(self.db) if self.db else None,
        }
        if AdeccoProvider:
            self.providers["adecco"] = AdeccoProvider()


_IMPLEMENTATION_MODULES = (
    acquisition,
    persistence,
    normalization_pipeline,
    matching,
    finalization,
)


class _SearchModule(types.ModuleType):
    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        for module in _IMPLEMENTATION_MODULES:
            if hasattr(module, name):
                setattr(module, name, value)


sys.modules[__name__].__class__ = _SearchModule

def get_search_service(db: Session) -> SearchService:
    return SearchService(db)
