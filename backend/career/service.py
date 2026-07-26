import hashlib
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from backend.career.completeness import analyze_profile
from backend.career.models import CandidateProfile
from backend.career.repository import CareerProfileRepository
from backend.career.schemas import (
    CareerProfileResponse,
    CareerProfileSummary,
    CareerProfileWrite,
)
from backend.resumes.models import ResumeDraft, ResumeVersion
from backend.storage.atomic import StorageWriteError, is_storage_exhaustion

_SEARCH_SNAPSHOT_VERSION = 1
_SEARCH_SNAPSHOT_MAX_CHARS = 32_000
_SEARCH_SNAPSHOT_MAX_FACTS = 128
_PRIVATE_FACT_TYPES = {"reference", "link"}
_RELEVANT_PREFERENCE_KEYS = (
    "available_from",
    "company_sizes",
    "company_values",
    "contract_types",
    "desired_benefits",
    "excluded_companies",
    "excluded_industries",
    "hard_max_distance_km",
    "notice_period_days",
    "preferred_languages",
    "preferred_locations",
    "preferred_work_modes",
    "relocation",
    "remote_only",
    "salary",
    "salary_min_chf",
    "target_industries",
    "target_roles",
    "travel_max_percent",
    "workload_max",
    "workload_min",
)
_PRIVATE_KEYS = {
    "address",
    "birth_date",
    "birthdate",
    "citizenship",
    "cittadinanza",
    "contact",
    "citoyennete",
    "contacts",
    "data_di_nascita",
    "date_de_naissance",
    "date_of_birth",
    "dob",
    "email",
    "geburtsdatum",
    "github",
    "linkedin",
    "link",
    "links",
    "mobile",
    "nationalite",
    "nationalities",
    "nationalitat",
    "nationality",
    "nazionalita",
    "permission_to_contact",
    "phone",
    "social",
    "socials",
    "staatsangehorigkeit",
    "telefon",
    "telefono",
    "telephone",
    "url",
    "urls",
    "website",
    "websites",
}
_EMAIL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@"
    r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9_-])"
)
_PHONE_PATTERN = re.compile(
    r"(?<![\w@])(?:\+?\d|\(\d)[\d\s()./-]{5,38}\d(?![\w@])"
)
_PHONE_YEAR_PATTERN = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
_PHONE_DATE_TIME_PATTERN = re.compile(
    r"(?:(?:19|20)\d{2}[-/.]\d{1,2}[-/.]\d{1,2}|"
    r"\d{1,2}[-/.]\d{1,2}[-/.](?:19|20)\d{2})"
    r"(?:\s+\d{1,2}[.-]\d{2})?"
)
_PHONE_CONTACT_CONTEXT_PATTERN = re.compile(
    r"(?i)(?:call|contact|mobile|phone|reach|tel(?:efon|ephone)?|"
    r"telefono|t[eé]l[eé]phone)\s*(?:me\s*)?(?:at|on|under|via)?\s*$"
)
_PHONE_NON_CONTACT_BEFORE_PATTERN = re.compile(
    r"(?i)(?:\b(?:build|commit|eur|chf|id|iso|issue|release|ticket|usd|version)\s*)$"
)
_PHONE_METRIC_AFTER_PATTERN = re.compile(
    r"(?i)^\s*(?:%|percent\b|(?:bytes?|chf|days?|eur|events?|gb|hours?|items?|"
    r"km|mb|metrics?|ms|projects?|records?|requests?|rows?|seconds?|users?|usd|years?)\b)"
)
_URL_PATTERN = re.compile(r"(?i)\b(?:https?://|www\.)[^\s,;]+")
_PRIVATE_LABEL_PATTERN = re.compile(
    r"(?i)\b(?:birth\s*date|date\s*of\s*birth|born|geburtsdatum|date\s*de\s*"
    r"naissance|data\s*di\s*nascita|nationality|citizenship|nationalit[aä]t|"
    r"nationalit[eé]|nazionalit[aà]|cittadinanza|phone|telephone|t[eé]l[eé]phone|"
    r"telefon|mobile|telefono)\s*[:=]\s*[^,;\n]+"
)


class CareerSearchSnapshotError(ValueError):
    """Raised when a Career Vault cannot provide a safe search snapshot."""


@dataclass(frozen=True)
class CareerSearchSnapshot:
    text: str
    profile_id: str
    profile_revision: int
    fact_ids: tuple[str, ...]
    sha256: str


def _private_snapshot_key(key: str) -> bool:
    camel_separated = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", key)
    ascii_key = (
        unicodedata.normalize("NFKD", camel_separated)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    normalized = re.sub(r"[^a-z0-9]+", "_", ascii_key.casefold()).strip("_")
    return (
        normalized in _PRIVATE_KEYS
        or normalized.endswith("_email")
        or normalized.endswith("_phone")
        or normalized.endswith("_address")
        or normalized.endswith("_url")
        or normalized.endswith("_website")
    )


def _redact_phone_candidates(text: str) -> str:
    """Redact bounded phone-like spans while preserving common dates and numeric metrics."""

    def replacement(match: re.Match[str]) -> str:
        candidate = match.group(0)
        digit_groups = re.findall(r"\d+", candidate)
        digits = "".join(digit_groups)
        if not 7 <= len(digits) <= 15:
            return candidate

        before = text[max(0, match.start() - 32) : match.start()]
        after = text[match.end() : min(len(text), match.end() + 24)]
        normalized = candidate.strip()
        strong_phone_signal = normalized.startswith(("+", "00", "0", "(")) or any(
            marker in normalized for marker in "()"
        )
        contact_context = _PHONE_CONTACT_CONTEXT_PATTERN.search(before) is not None

        if _PHONE_DATE_TIME_PATTERN.fullmatch(normalized):
            return candidate
        year_tokens = _PHONE_YEAR_PATTERN.findall(normalized)
        if len(year_tokens) >= 2:
            return candidate
        if (
            len(digit_groups) == 2
            and _PHONE_YEAR_PATTERN.fullmatch(digit_groups[0])
            and len(digit_groups[1]) <= 4
            and not strong_phone_signal
            and not contact_context
        ):
            return candidate

        if not strong_phone_signal and not contact_context:
            grouped_thousands = (
                len(digit_groups) >= 3
                and len(digit_groups[0]) == 1
                and all(len(group) == 3 for group in digit_groups[1:])
            )
            metric_context = (
                _PHONE_NON_CONTACT_BEFORE_PATTERN.search(before) is not None
                or _PHONE_METRIC_AFTER_PATTERN.search(after) is not None
            )
            if grouped_thousands or metric_context:
                return candidate

        if len(digit_groups) == 1:
            if len(digits) < 9 and not (strong_phone_signal or contact_context):
                return candidate
        elif len(digit_groups) == 2:
            first_length, second_length = map(len, digit_groups)
            plausible_pair = (first_length <= 3 and second_length >= 4) or (
                first_length == second_length == 4
            )
            if not (strong_phone_signal or contact_context or plausible_pair):
                return candidate

        return "[redacted-contact]"

    return _PHONE_PATTERN.sub(replacement, text)


def _bounded_snapshot_text(value: object, *, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = _EMAIL_PATTERN.sub("[redacted-contact]", text)
    text = _redact_phone_candidates(text)
    text = _URL_PATTERN.sub("[redacted-contact]", text)
    text = _PRIVATE_LABEL_PATTERN.sub("[redacted-private-field]", text)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _sanitize_snapshot_value(value: object, *, depth: int = 0) -> Any:
    if depth > 4 or value is None:
        return None
    if isinstance(value, str):
        return _bounded_snapshot_text(value, limit=1_200)
    if isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, list):
        sanitized = [
            _sanitize_snapshot_value(item, depth=depth + 1)
            for item in value[:24]
        ]
        return [item for item in sanitized if item not in (None, "", [], {})]
    if isinstance(value, dict):
        sanitized_dict: dict[str, Any] = {}
        for raw_key in sorted(value, key=lambda item: str(item).casefold()):
            key = str(raw_key)
            if _private_snapshot_key(key):
                continue
            item = _sanitize_snapshot_value(value[raw_key], depth=depth + 1)
            if item not in (None, "", [], {}):
                sanitized_dict[key] = item
        return sanitized_dict
    return _bounded_snapshot_text(value, limit=240)


def build_career_search_snapshot(profile: CandidateProfile) -> CareerSearchSnapshot:
    """Build a bounded, deterministic matching snapshot from confirmed Career Vault facts."""
    eligible_facts = sorted(
        (
            fact
            for fact in profile.facts
            if fact.archived_at is None
            and fact.verification_status == "confirmed"
            and fact.fact_type not in _PRIVATE_FACT_TYPES
        ),
        key=lambda fact: (int(fact.position), str(fact.id)),
    )
    if not eligible_facts:
        raise CareerSearchSnapshotError(
            "Career Vault search requires at least one confirmed, non-archived career fact."
        )

    raw_preferences = profile.preferences if isinstance(profile.preferences, dict) else {}
    preferences = {
        key: sanitized
        for key in _RELEVANT_PREFERENCE_KEYS
        if key in raw_preferences
        and (sanitized := _sanitize_snapshot_value(raw_preferences[key]))
        not in (None, "", [], {})
    }
    document: dict[str, Any] = {
        "eligible_fact_count": len(eligible_facts),
        "facts": [],
        "included_fact_count": 0,
        "headline": _bounded_snapshot_text(profile.headline, limit=500),
        "preferences": preferences,
        "snapshot_version": _SEARCH_SNAPSHOT_VERSION,
        "summary": _bounded_snapshot_text(profile.summary, limit=4_000),
    }
    included_fact_ids: list[str] = []
    for fact in eligible_facts[:_SEARCH_SNAPSHOT_MAX_FACTS]:
        entry = {
            "id": str(fact.id),
            "payload": _sanitize_snapshot_value(fact.payload),
            "position": int(fact.position),
            "type": str(fact.fact_type),
        }
        document["facts"].append(entry)
        document["included_fact_count"] = len(included_fact_ids) + 1
        candidate = json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        if len(candidate) > _SEARCH_SNAPSHOT_MAX_CHARS:
            document["facts"].pop()
            document["included_fact_count"] = len(included_fact_ids)
            break
        included_fact_ids.append(str(fact.id))

    if not included_fact_ids:
        raise CareerSearchSnapshotError(
            "Career Vault facts exceed the safe search snapshot limit; shorten the confirmed facts."
        )
    text = json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return CareerSearchSnapshot(
        text=text,
        profile_id=str(profile.id),
        profile_revision=int(profile.revision),
        fact_ids=tuple(included_fact_ids),
        sha256=digest,
    )

class CareerProfileService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = CareerProfileRepository(db)

    def get(self, user_id: int) -> CareerProfileResponse | None:
        profile = self.repository.get_by_user(user_id)
        return self._response(profile) if profile else None

    def search_snapshot(self, user_id: int) -> CareerSearchSnapshot:
        profile = self.repository.get_by_user(user_id)
        if profile is None:
            raise CareerSearchSnapshotError(
                "Career Vault search requires a saved Career Vault profile."
            )
        return build_career_search_snapshot(profile)

    def save(self, user_id: int, data: CareerProfileWrite) -> CareerProfileResponse:
        try:
            self._validate_resume_version_links(user_id, data)
            profile = self.repository.save(user_id, data)
            return self._response(profile)
        except Exception as exc:
            self.db.rollback()
            if is_storage_exhaustion(exc) and not isinstance(exc, StorageWriteError):
                raise StorageWriteError(
                    "Career Vault could not be saved because local storage is full."
                ) from exc
            raise

    def _validate_resume_version_links(
        self, user_id: int, data: CareerProfileWrite
    ) -> None:
        requested = {
            version_id
            for goal in data.goals
            for action in goal.payload.get("actions", [])
            for version_id in action.get("linked_resume_version_ids", [])
        }
        if not requested:
            return
        owned = {
            item[0]
            for item in (
                self.db.query(ResumeVersion.id)
                .join(ResumeDraft, ResumeVersion.draft_id == ResumeDraft.id)
                .join(CandidateProfile, ResumeDraft.profile_id == CandidateProfile.id)
                .filter(
                    CandidateProfile.user_id == user_id,
                    ResumeVersion.id.in_(requested),
                )
                .all()
            )
        }
        if requested - owned:
            raise ValueError("resume version links must belong to the same career profile")

    @staticmethod
    def _response(profile) -> CareerProfileResponse:
        response = CareerProfileResponse.model_validate(profile)
        return response.model_copy(update={"analysis": analyze_profile(response)})

    def summary(self, user_id: int) -> CareerProfileSummary | None:
        profile = self.repository.get_by_user(user_id)
        if profile is None:
            return None
        counts = Counter(item.fact_type for item in profile.facts)
        analysis = analyze_profile(profile)
        return CareerProfileSummary(
            id=profile.id,
            revision=profile.revision,
            display_name=profile.display_name,
            headline=profile.headline,
            fact_counts=dict(sorted(counts.items())),
            goal_count=len(profile.goals),
            completeness_score=analysis.completeness_score,
            issue_count=len(analysis.issues),
            updated_at=profile.updated_at,
        )
