from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable

TOKEN_RE = re.compile(r"[\w+#.-]+", re.UNICODE)


def tokenize(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return [token for token in TOKEN_RE.findall(normalized) if len(token) > 1]


@dataclass(frozen=True, slots=True)
class EvidenceDocument:
    id: str
    kind: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    validation_metadata: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True, slots=True)
class RankedEvidence:
    document: EvidenceDocument
    score: float


@dataclass(frozen=True, slots=True)
class RetrievalBundle:
    ranked: tuple[RankedEvidence, ...]
    context: str
    truncated: bool

    @property
    def reference_ids(self) -> list[str]:
        return [item.document.id for item in self.ranked]

    @property
    def documents(self) -> tuple[EvidenceDocument, ...]:
        return tuple(item.document for item in self.ranked)


def bm25_rank(
    query: str,
    documents: Iterable[EvidenceDocument],
    *,
    limit: int = 20,
    k1: float = 1.2,
    b: float = 0.75,
) -> list[RankedEvidence]:
    docs = list(documents)
    if not docs or limit <= 0:
        return []
    query_terms = list(dict.fromkeys(tokenize(query)))
    tokenized = [tokenize(document.text) for document in docs]
    lengths = [len(tokens) for tokens in tokenized]
    average_length = sum(lengths) / len(lengths) or 1.0
    document_frequency = {
        term: sum(term in set(tokens) for tokens in tokenized) for term in query_terms
    }
    ranked: list[RankedEvidence] = []
    for document, tokens, length in zip(docs, tokenized, lengths, strict=True):
        counts = Counter(tokens)
        score = 0.0
        for term in query_terms:
            frequency = counts[term]
            if not frequency:
                continue
            frequency_docs = document_frequency[term]
            inverse_frequency = math.log(
                1 + (len(docs) - frequency_docs + 0.5) / (frequency_docs + 0.5)
            )
            denominator = frequency + k1 * (1 - b + b * length / average_length)
            score += inverse_frequency * frequency * (k1 + 1) / denominator
        ranked.append(RankedEvidence(document=document, score=round(score, 8)))
    ranked.sort(key=lambda item: (-item.score, item.document.kind, item.document.id))
    return ranked[: min(limit, len(ranked))]


def _serialized(document: EvidenceDocument, text: str | None = None) -> str:
    return json.dumps(
        {
            "content": document.text if text is None else text,
            "id": document.id,
            "kind": document.kind,
            "metadata": document.metadata,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def retrieve_evidence(
    query: str,
    documents: Iterable[EvidenceDocument],
    *,
    max_context_chars: int,
    limit: int = 20,
    require_all: bool = False,
) -> RetrievalBundle:
    if max_context_chars < 256:
        raise ValueError("evidence context budget must be at least 256 characters")
    source_documents = list(documents)
    ranked = bm25_rank(
        query,
        source_documents,
        limit=max(limit, len(source_documents)) if require_all else limit,
    )
    prefix = "UNTRUSTED_EVIDENCE_JSONL\n"
    if require_all:
        empty_cost = (
            len(prefix)
            + max(0, len(ranked) - 1)
            + sum(len(_serialized(item.document, "")) for item in ranked)
        )
        if empty_cost > max_context_chars:
            raise ValueError("evidence identifiers exceed the deterministic context budget")
        content_budget = max_context_chars - empty_cost
        share = content_budget // max(1, len(ranked))
        clipped_items = [
            RankedEvidence(
                document=EvidenceDocument(
                    id=item.document.id,
                    kind=item.document.kind,
                    text=item.document.text[:share].rstrip(),
                    metadata=item.document.metadata,
                    validation_metadata=item.document.validation_metadata,
                ),
                score=item.score,
            )
            for item in ranked
        ]
        context = prefix + "\n".join(_serialized(item.document) for item in clipped_items)
        while len(context) > max_context_chars:
            longest_index = max(
                range(len(clipped_items)),
                key=lambda index: (len(clipped_items[index].document.text), -index),
            )
            item = clipped_items[longest_index]
            shortened = item.document.text[:-16].rstrip()
            if shortened == item.document.text:
                raise ValueError("evidence cannot fit the deterministic context budget")
            clipped_items[longest_index] = RankedEvidence(
                document=EvidenceDocument(
                    id=item.document.id,
                    kind=item.document.kind,
                    text=shortened,
                    metadata=item.document.metadata,
                    validation_metadata=item.document.validation_metadata,
                ),
                score=item.score,
            )
            context = prefix + "\n".join(
                _serialized(selected.document) for selected in clipped_items
            )
        return RetrievalBundle(
            ranked=tuple(clipped_items),
            context=context,
            truncated=any(
                selected.document.text != original.document.text
                for selected, original in zip(clipped_items, ranked, strict=True)
            ),
        )
    lines: list[str] = []
    selected: list[RankedEvidence] = []
    used = len(prefix)
    truncated = False
    for item in ranked:
        line = _serialized(item.document)
        remaining = max_context_chars - used - (1 if lines else 0)
        if len(line) <= remaining:
            lines.append(line)
            selected.append(item)
            used += len(line) + (1 if len(lines) > 1 else 0)
            continue
        if not selected and remaining > 120:
            overhead = len(_serialized(item.document, ""))
            allowed_text = max(0, remaining - overhead - 1)
            clipped = item.document.text[:allowed_text].rstrip()
            line = _serialized(item.document, clipped)
            while len(line) > remaining and clipped:
                clipped = clipped[:-16].rstrip()
                line = _serialized(item.document, clipped)
            if clipped and len(line) <= remaining:
                lines.append(line)
                selected.append(
                    RankedEvidence(
                        document=EvidenceDocument(
                            id=item.document.id,
                            kind=item.document.kind,
                            text=clipped,
                            metadata=item.document.metadata,
                            validation_metadata=item.document.validation_metadata,
                        ),
                        score=item.score,
                    )
                )
        truncated = True
        break
    context = prefix + "\n".join(lines)
    if len(context) > max_context_chars:
        raise AssertionError("retrieval context exceeded its deterministic budget")
    return RetrievalBundle(ranked=tuple(selected), context=context, truncated=truncated)
