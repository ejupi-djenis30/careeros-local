"""Compatibility import for the local search orchestrator.

The production implementation lives in :mod:`backend.search.orchestrator`.
Aliasing the module keeps established dependency injection and monkeypatch
paths working without retaining orchestration code in the legacy namespace.
"""

import sys

from backend.search import orchestrator as _orchestrator
from backend.search.orchestrator import SearchService, get_search_service

__all__ = ["SearchService", "get_search_service"]

sys.modules[__name__] = _orchestrator
