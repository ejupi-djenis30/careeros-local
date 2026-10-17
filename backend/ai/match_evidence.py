"""Stable match evidence API backed by the focused internal catalog."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from backend.ai.retrieval import EvidenceDocument

from .match_catalog import catalog as _catalog
from .match_catalog import documents as _documents
from .match_catalog.catalog import _atomic_quotes as _atomic_quotes
from .match_catalog.catalog import _coverage_complete as _coverage_complete
from .match_catalog.catalog import _quote_hash as _quote_hash
from .match_catalog.catalog import _source_fingerprint as _source_fingerprint
from .match_catalog.catalog import fingerprint_match_input_rows as fingerprint_match_input_rows
from .match_catalog.catalog import match_input_fingerprint as match_input_fingerprint
from .match_catalog.catalog import match_quote_bindings as match_quote_bindings
from .match_catalog.clause_types import _ClauseSegment as _ClauseSegment
from .match_catalog.clause_types import _ConnectorKind as _ConnectorKind
from .match_catalog.clause_types import _MarkerDirection as _MarkerDirection
from .match_catalog.clauses import _anaphoric_reassertion as _anaphoric_reassertion
from .match_catalog.clauses import _annotate_explicit_status as _annotate_explicit_status
from .match_catalog.clauses import _apply_absence_scope as _apply_absence_scope
from .match_catalog.clauses import _apply_status_propagation as _apply_status_propagation
from .match_catalog.clauses import _classification_text as _classification_text
from .match_catalog.clauses import _classify_clause_commas as _classify_clause_commas
from .match_catalog.clauses import _connector_kind as _connector_kind
from .match_catalog.clauses import _has_requirement_subject as _has_requirement_subject
from .match_catalog.clauses import _marker_direction as _marker_direction
from .match_catalog.clauses import _positive_reassertion as _positive_reassertion
from .match_catalog.clauses import _raw_clause_segments as _raw_clause_segments
from .match_catalog.clauses import _structured_clauses as _structured_clauses
from .match_catalog.constants import _CANDIDATE_EVIDENCE_CHARS as _CANDIDATE_EVIDENCE_CHARS
from .match_catalog.constants import _DIMENSION_PATTERNS as _DIMENSION_PATTERNS
from .match_catalog.constants import _DIMENSIONS as _DIMENSIONS
from .match_catalog.constants import _FRAGMENT_SPLIT as _FRAGMENT_SPLIT
from .match_catalog.constants import _JOB_EVIDENCE_CHARS as _JOB_EVIDENCE_CHARS
from .match_catalog.constants import (
    _MAX_PROMPT_QUOTES_PER_DIMENSION as _MAX_PROMPT_QUOTES_PER_DIMENSION,
)
from .match_catalog.constants import _MAX_QUOTE_CHARS as _MAX_QUOTE_CHARS
from .match_catalog.constants import _REQUIREMENT_STATUS_PATTERNS as _REQUIREMENT_STATUS_PATTERNS
from .match_catalog.fragments import _all_fragments as _all_fragments
from .match_catalog.fragments import _explicit_requirement_status as _explicit_requirement_status
from .match_catalog.fragments import _has_positive_evidence as _has_positive_evidence
from .match_catalog.fragments import _is_missing_evidence as _is_missing_evidence
from .match_catalog.fragments import _matching_fragments as _matching_fragments
from .match_catalog.fragments import _quote_fragments as _quote_fragments
from .match_catalog.fragments import _requirement_status as _requirement_status
from .match_catalog.fragments import _segment_fragment as _segment_fragment
from .match_catalog.fragments import _skill_evidence as _skill_evidence
from .match_catalog.grammar_patterns import (
    _CLASSIFICATION_CONTRACTIONS as _CLASSIFICATION_CONTRACTIONS,
)
from .match_catalog.grammar_patterns import (
    _CLAUSE_GRAMMAR_PRONOUN_PATTERN as _CLAUSE_GRAMMAR_PRONOUN_PATTERN,
)
from .match_catalog.grammar_patterns import _FORWARD_MODAL_MARKER as _FORWARD_MODAL_MARKER
from .match_catalog.grammar_patterns import _MODAL_ACTION_WORD_PATTERN as _MODAL_ACTION_WORD_PATTERN
from .match_catalog.grammar_patterns import _PASSIVE_MODAL_MARKER as _PASSIVE_MODAL_MARKER
from .match_catalog.grammar_patterns import _REASSERTION_GRAMMARS as _REASSERTION_GRAMMARS
from .match_catalog.grammar_patterns import (
    _STRUCTURAL_CONNECTOR_PATTERN as _STRUCTURAL_CONNECTOR_PATTERN,
)
from .match_catalog.grammar_patterns import (
    _STRUCTURED_EXCLUSION_GRAMMARS as _STRUCTURED_EXCLUSION_GRAMMARS,
)
from .match_catalog.requirements import _languages as _languages
from .match_catalog.requirements import _qualification_rank as _qualification_rank
from .match_catalog.requirements import _required_value_groups as _required_value_groups
from .match_catalog.requirements import _requirement_summary as _requirement_summary
from .match_catalog.requirements import _segment_skill_terms as _segment_skill_terms
from .match_catalog.requirements import _segment_skill_text as _segment_skill_text
from .match_catalog.requirements import _years as _years
from .match_catalog.skill_terms import _skill_parse_text as _skill_parse_text
from .match_catalog.skill_terms import _skill_term_mentions as _skill_term_mentions
from .match_catalog.skill_terms import _skill_terms as _skill_terms
from .match_catalog.stopwords import _SKILL_STOPWORDS as _SKILL_STOPWORDS
from .match_catalog.value_patterns import _CEFR_RANK as _CEFR_RANK
from .match_catalog.value_patterns import _LANGUAGE_ALIAS_PATTERN as _LANGUAGE_ALIAS_PATTERN
from .match_catalog.value_patterns import _LANGUAGE_ALIASES as _LANGUAGE_ALIASES
from .match_catalog.value_patterns import _LANGUAGE_LEVEL_PATTERN as _LANGUAGE_LEVEL_PATTERN
from .match_catalog.value_patterns import _NUMBER_WORDS as _NUMBER_WORDS
from .match_catalog.value_patterns import _QUALIFICATION_PATTERNS as _QUALIFICATION_PATTERNS
from .match_catalog.value_patterns import _YEARS_PATTERN as _YEARS_PATTERN

MATCH_EVIDENCE_CATALOG_VERSION = "8"
MATCH_EVIDENCE_DESCRIPTION_CHARS = 6_000


def _catalog_fingerprint(
    quotes: Mapping[str, Mapping[str, Any]],
    *,
    requirement_summary: Mapping[str, Any],
    coverage_complete: Mapping[str, bool],
) -> str:
    return _catalog._catalog_fingerprint(
        quotes,
        requirement_summary=requirement_summary,
        coverage_complete=coverage_complete,
        catalog_version=MATCH_EVIDENCE_CATALOG_VERSION,
    )


def candidate_evidence_document(profile: Mapping[str, Any]) -> EvidenceDocument:
    return _documents.candidate_evidence_document(
        profile, catalog_version=MATCH_EVIDENCE_CATALOG_VERSION
    )


def job_evidence_document(
    job: Mapping[str, Any],
    row_index: int,
    *,
    description_limit: int,
) -> EvidenceDocument:
    return _documents.job_evidence_document(
        job,
        row_index,
        description_limit=description_limit,
        catalog_version=MATCH_EVIDENCE_CATALOG_VERSION,
        description_chars=MATCH_EVIDENCE_DESCRIPTION_CHARS,
    )
