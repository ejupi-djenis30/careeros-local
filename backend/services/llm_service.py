"""Compatibility import for the local AI pipeline.

New code must import task contracts and orchestration from :mod:`backend.ai`.
The module alias preserves legacy monkeypatch and import paths while the desktop
search workflow is migrated one capability at a time.
"""

import sys

from backend.ai import pipeline as _pipeline
from backend.ai.pipeline import LLMService, _unwrap_retry_error, llm_service

__all__ = ["LLMService", "_unwrap_retry_error", "llm_service"]

sys.modules[__name__] = _pipeline
