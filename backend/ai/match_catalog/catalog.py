"""Canonical evidence quote catalogs, bindings and fingerprints."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from backend.ai.retrieval import EvidenceDocument
from backend.services.search.prompt_compaction import compact_prompt_text

from .constants import _DIMENSIONS, _MAX_PROMPT_QUOTES_PER_DIMENSION, _MAX_QUOTE_CHARS
from .fragments import _has_positive_evidence, _quote_fragments, _requirement_status


def _source_fingerprint(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _quote_hash(dimension: str, text: str) -> str:
    return hashlib.sha256(f"{dimension}\0{text}".encode("utf-8")).hexdigest()


def _catalog_fingerprint(
    quotes: Mapping[str, Mapping[str, Any]],
    *,
    requirement_summary: Mapping[str, Any],
    coverage_complete: Mapping[str, bool],
    catalog_version: str,
) -> str:
    return _source_fingerprint(
        {
            "catalog_version": catalog_version,
            "quotes": {
                quote_id: {
                    "dimension": quote.get("dimension"),
                    "has_positive_evidence": quote.get("has_positive_evidence"),
                    "requirement_status": quote.get("requirement_status"),
                    "text_hash": quote.get("text_hash"),
                }
                for quote_id, quote in sorted(quotes.items())
            },
            "coverage_complete": dict(sorted(coverage_complete.items())),
            "requirement_summary": requirement_summary,
        }
    )


def _coverage_complete(
    dimensions: Mapping[str, str],
    *,
    source_kind: str,
) -> dict[str, bool]:
    # The complete server-side clause catalog and summaries are independent of
    # the bounded prompt projection. A long CV or more than four CV clauses must
    # never force a neutral score merely because the model sees a compact view.
    _ = dimensions, source_kind
    return {dimension: True for dimension in _DIMENSIONS}


def _atomic_quotes(
    base_id: str,
    dimensions: Mapping[str, str],
    *,
    max_document_chars: int,
    source_kind: str,
) -> tuple[str, dict[str, dict[str, Any]]]:
    """Build a compact, bounded quote catalog while preserving every dimension.

    One quote per dimension is reserved first. Additional fragments are admitted in
    round-robin order so a later sentence (for example a concrete skill) remains
    selectable without allowing long CVs or job ads to consume the model context.
    """
    candidates = {
        dimension: _quote_fragments(
            str(dimensions.get(dimension) or ""),
            f"No explicit {dimension} evidence.",
        )
        for dimension in _DIMENSIONS
    }
    quotes: dict[str, dict[str, Any]] = {}
    lines = ["ATOMIC_EVIDENCE_QUOTES"]

    for dimension in _DIMENSIONS:
        for fragment_index, fragment in enumerate(candidates[dimension]):
            quote_id = f"{base_id}:{dimension}:{fragment_index}"
            quotes[quote_id] = {
                "dimension": dimension,
                "has_positive_evidence": _has_positive_evidence(fragment, source_kind=source_kind),
                "requirement_status": _requirement_status(fragment),
                "text": fragment,
                "text_hash": _quote_hash(dimension, fragment),
            }

    def add_prompt_quote(dimension: str, fragment_index: int) -> bool:
        fragment = candidates[dimension][fragment_index]
        quote_id = f"{base_id}:{dimension}:{fragment_index}"
        line = f"{quote_id} | {compact_prompt_text(fragment, _MAX_QUOTE_CHARS)}"
        projected = "\n".join((*lines, line))
        if len(projected) > max_document_chars:
            return False
        lines.append(line)
        return True

    for dimension in _DIMENSIONS:
        if not add_prompt_quote(dimension, 0):
            raise ValueError("atomic evidence budget cannot represent every match dimension")
    for fragment_index in range(1, _MAX_PROMPT_QUOTES_PER_DIMENSION):
        for dimension in _DIMENSIONS:
            if fragment_index < len(candidates[dimension]):
                add_prompt_quote(dimension, fragment_index)
    text = "\n".join(lines)
    if len(text) > max_document_chars:
        raise AssertionError("atomic evidence exceeded its deterministic document budget")
    return text, quotes


def match_input_fingerprint(
    candidate: EvidenceDocument,
    job: EvidenceDocument,
) -> str:
    canonical = json.dumps(
        {
            "candidate": {
                "catalog_fingerprint": candidate.validation_metadata.get("catalog_fingerprint"),
                "catalog_version": candidate.validation_metadata.get("catalog_version"),
                "id": candidate.id,
                "source_fingerprint": candidate.validation_metadata.get("source_fingerprint"),
            },
            "job": {
                "catalog_fingerprint": job.validation_metadata.get("catalog_fingerprint"),
                "catalog_version": job.validation_metadata.get("catalog_version"),
                "id": job.id,
                "source_fingerprint": job.validation_metadata.get("source_fingerprint"),
            },
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def match_quote_bindings(
    candidate: EvidenceDocument,
    job: EvidenceDocument,
) -> dict[str, dict[str, Any]]:
    bindings: dict[str, dict[str, Any]] = {}
    for document in (candidate, job):
        quotes = document.validation_metadata.get("quotes")
        if not isinstance(quotes, Mapping):
            continue
        for quote_id, quote in quotes.items():
            if isinstance(quote_id, str) and isinstance(quote, Mapping):
                bindings[quote_id] = dict(quote)
    return bindings


def fingerprint_match_input_rows(
    evidence: Sequence[EvidenceDocument],
) -> list[str]:
    candidate = next((item for item in evidence if item.id == "candidate:profile"), None)
    if candidate is None:
        return []
    jobs = sorted(
        (item for item in evidence if item.kind == "job" and item.id.startswith("job:")),
        key=lambda item: int(item.id.split(":", 1)[1]),
    )
    return [match_input_fingerprint(candidate, job) for job in jobs]
