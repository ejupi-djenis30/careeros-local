"""Evidence grounding and server-owned fit policy for external proposals."""

from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from backend.agent_work.context import canonical_json_bytes
from backend.agent_work.errors import AgentWorkError
from backend.agent_work.models import AgentWorkRequest
from backend.agent_work.schemas import (
    MAX_RESULT_BYTES,
    AnalysisProposalPayload,
    DiscoveryProposalPayload,
    MaterialsProposalPayload,
    ProposalPayload,
    WorkGate,
    WorkScores,
)
from backend.ai.grounding import validate_grounding
from backend.ai.retrieval import EvidenceDocument, tokenize

DIMENSIONS = ("role", "requirements", "language", "location", "contract", "freshness")
WEIGHTS = (25, 30, 15, 15, 10, 5)

_ROLE_TERMS = frozenset(
    {
        "architect",
        "consultant",
        "developer",
        "engineer",
        "lead",
        "manager",
        "specialist",
        "analyst",
        "director",
        "designer",
        "administrator",
    }
)
_LANGUAGE_TERMS = frozenset(
    {
        "english",
        "german",
        "deutsch",
        "french",
        "français",
        "francais",
        "italian",
        "italiano",
        "spanish",
        "español",
        "bilingual",
        "fluent",
        "language",
        "languages",
    }
)
_LOCATION_TERMS = frozenset(
    {
        "remote",
        "hybrid",
        "onsite",
        "on-site",
        "relocation",
        "switzerland",
        "schweiz",
        "suisse",
        "svizzera",
    }
)
_CONTRACT_TERMS = frozenset(
    {
        "permanent",
        "temporary",
        "contract",
        "freelance",
        "internship",
        "apprenticeship",
        "full-time",
        "part-time",
        "fulltime",
        "parttime",
        "workload",
    }
)
_FRESHNESS_TERMS = frozenset(
    {"posted", "published", "today", "yesterday", "recent", "recently", "new", "ago"}
)
_EXPLICIT_NEGATION = re.compile(
    r"\bnot\s+(?:strictly\s+)?required\b"
    r"|\bno\b.{0,40}\b(?:required|needed|mandatory)\b"
    r"|\bwithout\b|\bnicht\s+erforderlich\b|\bnon\s+requis(?:e)?\b"
    r"|\bnon\s+richiest[oa]\b|\bsenza\b",
    re.IGNORECASE,
)


def fit_score(scores: WorkScores) -> int:
    weighted = sum(
        getattr(scores, key).score * weight for key, weight in zip(DIMENSIONS, WEIGHTS, strict=True)
    )
    return int((Decimal(weighted) / Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def eligibility(gates: list[WorkGate]) -> str:
    if any(g.status == "reject" for g in gates):
        return "reject"
    if any(g.status == "hold" or g.unknowns for g in gates):
        return "hold"
    return "eligible"


def validate_proposal_size(payload: ProposalPayload) -> None:
    if len(canonical_json_bytes(payload.model_dump(mode="json"))) > MAX_RESULT_BYTES:
        raise AgentWorkError("invalid_result", "Proposal exceeds the supported byte limit")


def _evidence(context: dict[str, Any]) -> list[EvidenceDocument]:
    return [
        EvidenceDocument(
            id=fact["id"], kind=fact["kind"], text=canonical_json_bytes(fact).decode("utf-8")
        )
        for fact in context.get("facts", [])
    ]


def _ground(context: dict[str, Any], text: str, fact_ids: list[str]) -> None:
    if not fact_ids or validate_grounding(
        {"claims": [{"text": text, "fact_ids": fact_ids}], "fact_citations": fact_ids},
        _evidence(context),
    ):
        raise AgentWorkError(
            "evidence_invalid", "A career assertion is not supported by its cited facts"
        )


def _requirement_supported_by_quote(requirement: str, quote: str) -> bool:
    normalized_requirement = re.sub(r"\s+", " ", requirement.casefold()).strip(" .,:;")
    normalized_quote = re.sub(r"\s+", " ", quote.casefold()).strip(" .,:;")
    return (
        bool(normalized_requirement)
        and normalized_requirement in normalized_quote
        and _EXPLICIT_NEGATION.search(quote) is None
    )


def _tokens(value: object) -> set[str]:
    return {token.strip(".-").casefold() for token in tokenize(str(value or ""))}


def _preference_tokens(context: Mapping[str, Any], *fields: str) -> set[str]:
    preferences = context.get("preferences")
    if not isinstance(preferences, Mapping):
        return set()
    values: list[str] = []
    for field in fields:
        value = preferences.get(field)
        if isinstance(value, list):
            values.extend(str(item) for item in value)
        elif field == "remote_only" and value is True:
            values.append("remote")
        elif value not in (None, False, ""):
            values.append(str(value))
    return _tokens(" ".join(values))


def _cited_fact_tokens(
    context: Mapping[str, Any], fact_ids: list[str], *, kind: str
) -> set[str]:
    selected = set(fact_ids)
    values: list[str] = []
    for fact in context.get("facts", []):
        if not isinstance(fact, Mapping) or fact.get("id") not in selected or fact.get("kind") != kind:
            continue
        values.extend(
            str(fact.get(field) or "") for field in ("title", "description", "attributes")
        )
    return _tokens(" ".join(values))


def _quote_supports_dimension(
    dimension: str,
    quote: str,
    *,
    source: Mapping[str, Any],
    context: Mapping[str, Any],
    fact_ids: list[str],
) -> bool:
    """Classify a frozen source excerpt without trusting the proposed dimension label."""

    quote_terms = _tokens(quote)
    if not quote_terms or _EXPLICIT_NEGATION.search(quote):
        return False
    title_terms = _tokens(source.get("title"))
    location_terms = _tokens(source.get("location")) | _preference_tokens(
        context, "preferred_locations", "preferred_work_modes", "remote_only"
    )
    contract_terms = _preference_tokens(context, "contract_types") | _CONTRACT_TERMS
    language_terms = _LANGUAGE_TERMS | _cited_fact_tokens(
        context, fact_ids, kind="language"
    ) | {
        term for term in quote_terms if re.fullmatch(r"[abc][12]", term)
    }
    freshness = bool(
        quote_terms & _FRESHNESS_TERMS
        or re.search(r"\b\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?\b", quote)
    )
    if dimension == "role":
        return bool(quote_terms & _ROLE_TERMS or (title_terms and quote_terms <= title_terms))
    if dimension == "language":
        return bool(quote_terms & language_terms)
    if dimension == "location":
        return bool(quote_terms & (_LOCATION_TERMS | location_terms))
    if dimension == "contract":
        return bool(
            quote_terms & contract_terms
            or re.search(r"\b\d{1,3}\s*%", quote)
        )
    if dimension == "freshness":
        return freshness
    if dimension == "requirements":
        if re.search(r"\b\d+\+?\s+(?:years?|ans?|jahre[n]?|anni)\b", quote, re.IGNORECASE):
            return True
        specialized = language_terms | _LOCATION_TERMS | location_terms | contract_terms | _FRESHNESS_TERMS
        substantive = quote_terms - {
            "required",
            "requirement",
            "requirements",
            "needed",
            "mandatory",
            "preferred",
            "experience",
            "knowledge",
            "skill",
            "skills",
        }
        return bool(substantive) and not substantive <= (specialized | _ROLE_TERMS)
    return False


def _gates(
    context: dict[str, Any],
    gates: list[WorkGate],
    scores: WorkScores,
    source: Mapping[str, Any],
) -> None:
    if len(gates) != 6 or {g.dimension for g in gates} != set(DIMENSIONS):
        raise AgentWorkError("invalid_result", "Exactly one gate per fit dimension is required")
    allowed = {fact["id"] for fact in context.get("facts", [])}
    source_text = "\n".join(
        str(source.get(field) or "")
        for field in ("title", "description", "location", "workload")
        if source.get(field)
    )
    for gate in gates:
        if not set(gate.fact_ids).issubset(allowed) or any(
            not quote.strip() or quote not in source_text for quote in gate.quote_references
        ):
            raise AgentWorkError(
                "evidence_invalid", "Gate evidence is not present in the frozen context"
            )
        if gate.status == "eligible":
            cited = [fact for fact in context.get("facts", []) if fact["id"] in gate.fact_ids]
            preferences = context.get("preferences") or {}
            if gate.dimension == "language" and not any(
                fact["kind"] == "language" for fact in cited
            ):
                raise AgentWorkError(
                    "evidence_invalid", "Language eligibility requires a confirmed language fact"
                )
            if gate.dimension == "location" and not any(
                preferences.get(key)
                for key in ("preferred_locations", "preferred_work_modes", "remote_only")
            ):
                raise AgentWorkError(
                    "evidence_invalid",
                    "Unknown location preferences cannot support an eligible gate",
                )
            if gate.dimension == "contract" and not preferences.get("contract_types"):
                raise AgentWorkError(
                    "evidence_invalid",
                    "Unknown contract preferences cannot support an eligible gate",
                )
        score = getattr(scores, gate.dimension)
        if gate.unknowns:
            if gate.status == "eligible" or score.score != 0:
                raise AgentWorkError(
                    "invalid_result", "Unknown dimensions require a hold/reject gate and zero score"
                )
        elif gate.status == "hold":
            raise AgentWorkError(
                "invalid_result", "A hold gate must explain the unknown information"
            )
        elif not gate.quote_references:
            raise AgentWorkError("evidence_invalid", "A resolved gate requires source evidence")
        elif any(
            not _quote_supports_dimension(
                gate.dimension,
                quote,
                source=source,
                context=context,
                fact_ids=gate.fact_ids,
            )
            for quote in gate.quote_references
        ):
            raise AgentWorkError(
                "evidence_invalid",
                "A gate quotation does not support its declared fit dimension",
            )
        if gate.status == "eligible" and gate.dimension in {"location", "contract"}:
            preference_fields = (
                ("preferred_locations", "preferred_work_modes", "remote_only")
                if gate.dimension == "location"
                else ("contract_types",)
            )
            expected_terms = _preference_tokens(context, *preference_fields)
            if not expected_terms or not any(
                _tokens(quote) & expected_terms for quote in gate.quote_references
            ):
                raise AgentWorkError(
                    "evidence_invalid",
                    f"The {gate.dimension} gate does not match the candidate preferences",
                )
        if (
            gate.status == "eligible"
            and gate.dimension in {"role", "requirements", "language"}
            and not gate.fact_ids
        ):
            raise AgentWorkError(
                "evidence_invalid", "An eligible career gate requires confirmed candidate evidence"
            )
        if gate.status == "eligible" and gate.dimension in {"role", "requirements", "language"}:
            for quote in gate.quote_references:
                _ground(context, quote, gate.fact_ids)
    # Overall is derived rather than trusted, including persisted and returned payloads.
    scores.overall_score = fit_score(scores)


def validate_discovery_proposal(
    request: AgentWorkRequest, payload: DiscoveryProposalPayload
) -> None:
    for vacancy in payload.listings:
        _gates(
            request.context_snapshot,
            vacancy.gates,
            vacancy.scores,
            {
                "title": vacancy.title,
                "description": vacancy.source_text,
                "location": vacancy.location,
            },
        )


def validate_analysis_proposal(request: AgentWorkRequest, payload: AnalysisProposalPayload) -> None:
    context = request.context_snapshot
    target = context.get("target_job") or {}
    _gates(context, payload.gates, payload.scores, target)
    source = target.get("description") or ""
    outcome = eligibility(payload.gates)
    if outcome != "eligible" and payload.recommendation in {"strong_fit", "consider"}:
        raise AgentWorkError("invalid_result", "A held or rejected gate cannot recommend applying")
    for claim in payload.claims:
        _ground(context, claim.claim_text, claim.fact_ids)
        if claim.quote_text and claim.quote_text not in source:
            raise AgentWorkError(
                "evidence_invalid", "A quotation is not present in the target advert"
            )


def validate_materials_proposal(
    request: AgentWorkRequest, payload: MaterialsProposalPayload
) -> None:
    context = request.context_snapshot
    allowed = {fact["id"] for fact in context.get("facts", [])}
    selected = set(payload.cv_selected_fact_ids)
    if len(selected) != len(payload.cv_selected_fact_ids) or not selected.issubset(allowed):
        raise AgentWorkError("evidence_invalid", "Selected CV facts are unavailable")
    preset = context.get("preset") or {}
    if (payload.preset_id, payload.preset_version, payload.locale) != (
        preset.get("id"),
        preset.get("version"),
        preset.get("locale"),
    ):
        raise AgentWorkError("invalid_result", "Materials must use the reviewed template selection")
    material_items = [
        *payload.cv_cited_overrides,
        *payload.cover_letter,
        *payload.email.body,
        *payload.questions_answers,
    ]
    if len({item.id for item in material_items}) != len(material_items):
        raise AgentWorkError("invalid_result", "Material claim identities must be unique")
    override_targets: set[tuple[str, ...]] = set()
    for override in payload.cv_cited_overrides:
        target = tuple(sorted(set(override.fact_ids)))
        if target in override_targets:
            raise AgentWorkError("invalid_result", "CV overrides must target different fact blocks")
        override_targets.add(target)
    for item in material_items:
        cited = set(item.fact_ids)
        if len(cited) != len(item.fact_ids) or not cited.issubset(selected):
            raise AgentWorkError(
                "evidence_invalid", "Material citations must belong to the selected CV facts"
            )
        _ground(context, item.text, item.fact_ids)
    source = (context.get("target_job") or {}).get("description") or ""
    for requirement in payload.requirements_to_evidence:
        cited = set(requirement.fact_ids)
        if (
            requirement.quote_text not in source
            or len(cited) != len(requirement.fact_ids)
            or not cited.issubset(selected)
            or not _requirement_supported_by_quote(
                requirement.requirement, requirement.quote_text
            )
        ):
            raise AgentWorkError("evidence_invalid", "Requirement evidence is unavailable")
        _ground(context, requirement.requirement, requirement.fact_ids)


def validate_proposal_payload(request: AgentWorkRequest, payload: ProposalPayload) -> None:
    validate_proposal_size(payload)
    if payload.kind != request.work_kind:
        raise AgentWorkError("invalid_result", "Proposal kind does not match its work request")
    if isinstance(payload, DiscoveryProposalPayload):
        validate_discovery_proposal(request, payload)
    elif isinstance(payload, AnalysisProposalPayload):
        validate_analysis_proposal(request, payload)
    elif isinstance(payload, MaterialsProposalPayload):
        validate_materials_proposal(request, payload)
