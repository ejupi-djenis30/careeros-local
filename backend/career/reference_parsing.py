"""Focused reference and preference parsing for CareerOS Vault reference import."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from backend.career.payloads import CareerPreferences
from backend.career.schemas import PreferenceCandidate, PreferenceField

MAX_REVIEW_MESSAGES = 50
MAX_PREFERENCE_CANDIDATES = 24


class _MessageBuffer(list[str]):
    def __init__(self) -> None:
        super().__init__()
        self.omitted = 0

    def append(self, message: str) -> None:
        if len(self) < MAX_REVIEW_MESSAGES - 1:
            super().append(message)
        else:
            self.omitted += 1

    def bounded(self, *, label: str) -> list[str]:
        messages = list(self)
        if self.omitted:
            messages.append(
                f"{self.omitted} additional {label} omitted because the response limit was reached."
            )
        return messages


class _CandidateBuffer(list[PreferenceCandidate]):
    def __init__(self) -> None:
        super().__init__()
        self.omitted = 0

    def append(self, candidate: PreferenceCandidate) -> None:
        if len(self) < MAX_PREFERENCE_CANDIDATES:
            super().append(candidate)
        else:
            self.omitted += 1


class SourceImportError(ValueError):
    pass


_UNSAFE_EXTENSIONS = {
    ".py",
    ".sh",
    ".bash",
    ".js",
    ".mjs",
    ".ts",
    ".tsx",
    ".jsx",
    ".bat",
    ".cmd",
    ".ps1",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".vbs",
    ".env",
    ".pem",
    ".key",
    ".cer",
    ".crt",
    ".pfx",
    ".p12",
}

_UNSAFE_FILENAMES = {
    "id_rsa",
    "id_ed25519",
    "id_dsa",
    "id_ecdsa",
    ".env",
    "credentials",
    "credentials.json",
    "shadow",
    "passwd",
    "secrets",
    "secret",
}

_SECRET_PATTERNS = [
    re.compile(rb"-----BEGIN [A-Z0-9_\-\s]+PRIVATE KEY"),
    re.compile(rb"-----BEGIN [A-Z0-9_\-\s]+CERTIFICATE"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"ghp_[A-Za-z0-9_]{36}"),
]


def validate_safe_source_input(filename: str, data: bytes) -> None:
    """Validate that the uploaded source is safe and does not contain scripts or secrets.

    Error messages intentionally omit file contents and matched secret values.
    """
    clean_name = str(filename or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
    base_stem = clean_name.split(".")[0] if clean_name else ""

    for suffix in Path(clean_name).suffixes:
        if suffix in _UNSAFE_EXTENSIONS:
            raise SourceImportError("Unsupported or unsafe file type rejected")

    if base_stem in _UNSAFE_FILENAMES or clean_name in _UNSAFE_FILENAMES:
        raise SourceImportError("Unsupported or credential file rejected")

    if data.startswith(b"#!"):
        raise SourceImportError("Executable script files cannot be imported")

    for pattern in _SECRET_PATTERNS:
        if pattern.search(data):
            raise SourceImportError(
                "File contains credential or private secret material and cannot be imported"
            )

    # Check for binary control characters in text documents (excluding tab, newline, CR)
    # Control chars 0-8, 11-12, 14-31, 127
    if clean_name.endswith((".txt", ".md")):
        for byte in data:
            if (byte < 32 and byte not in (9, 10, 13)) or byte == 127:
                raise SourceImportError(
                    "Text file contains unsupported binary or control characters"
                )


def extract_docx_text_in_document_order(data: bytes, max_chars: int) -> str:
    """Extract DOCX text traversing paragraphs and nested/merged tables once in document order."""
    word_document = Document(BytesIO(data))
    # Retain the actual XML elements. Keeping only ``id(element)`` lets Python
    # recycle proxy IDs while traversing large tables and silently drops cells.
    seen_cells: set[Any] = set()
    parts: list[str] = []
    running_chars = 0

    def _traverse_container(container: Any, depth: int = 0) -> None:
        nonlocal running_chars
        if depth > 20:
            raise SourceImportError("The DOCX document exceeds nested table depth limits")
        for child in container:
            tag = child.tag.split("}")[-1]
            if tag == "p":
                text = Paragraph(child, word_document).text.strip()
                if text:
                    running_chars += len(text) + 1
                    if running_chars > max_chars:
                        raise SourceImportError(
                            "Extracted source text exceeds the configured safety limit"
                        )
                    parts.append(text)
            elif tag == "tbl":
                table = Table(child, word_document)
                for row in table.rows:
                    for cell in row.cells:
                        cell_element = cell._tc
                        if cell_element in seen_cells:
                            continue
                        seen_cells.add(cell_element)
                        if len(seen_cells) > 2000:
                            raise SourceImportError(
                                "The DOCX document exceeds table complexity limits"
                            )
                        _traverse_container(cell._tc, depth + 1)

    _traverse_container(word_document.element.body, 0)
    return "\n\n".join(parts)


def _preference_candidate_id(locator: str, field: str, value: Any) -> str:
    canonical = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(f"{locator}\0{field}\0{canonical}".encode("utf-8")).hexdigest()


_WORK_MODE_MAP = {
    "onsite": "onsite",
    "in sede": "onsite",
    "in-person": "onsite",
    "in person": "onsite",
    "hybrid": "hybrid",
    "ibrido": "hybrid",
    "remote": "remote",
    "da remoto": "remote",
    "remoto": "remote",
}

_CONTRACT_TYPE_MAP = {
    "permanent": "permanent",
    "indeterminato": "permanent",
    "tempo indeterminato": "permanent",
    "temporary": "temporary",
    "determinato": "temporary",
    "tempo determinato": "temporary",
    "contract": "contract",
    "contratto": "contract",
    "fixed-term": "contract",
    "freelance": "freelance",
    "libero professionista": "freelance",
    "partita iva": "freelance",
    "internship": "internship",
    "stage": "internship",
    "tirocinio": "internship",
    "apprenticeship": "apprenticeship",
    "apprendistato": "apprenticeship",
}


def bound_review_messages(messages: list[str], *, label: str) -> list[str]:
    """Keep response messages inside the wire limit and disclose omissions."""
    if len(messages) <= MAX_REVIEW_MESSAGES:
        return messages
    retained = messages[: MAX_REVIEW_MESSAGES - 1]
    omitted = len(messages) - len(retained)
    retained.append(f"{omitted} additional {label} omitted because the response limit was reached.")
    return retained


def _whole_integer(raw: str, *, unit_pattern: str = "") -> int | None:
    suffix = rf"(?:\s*(?:{unit_pattern}))?" if unit_pattern else ""
    match = re.fullmatch(rf"\s*(\d+){suffix}\s*", raw, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def _whole_distance(raw: str) -> float | None:
    match = re.fullmatch(
        r"\s*(\d+(?:\.\d+)?)\s*(?:km|kilomet(?:er|re)s?)?\s*",
        raw,
        flags=re.IGNORECASE,
    )
    return float(match.group(1)) if match else None


def _unsupported_value(review_notes: list[str], field: str, value: str, source: str) -> None:
    review_notes.append(
        f"Unsupported value '{value[:80]}' for {field} in '{source[:120]}'; field was not imported."
    )


def parse_goal_preferences(
    text: str,
) -> tuple[list[PreferenceCandidate], list[str], list[str]]:
    """Parse explicit typed preference candidates from goals reference text.

    Returns (preference_candidates, review_notes, warnings).
    """
    candidates = _CandidateBuffer()
    review_notes = _MessageBuffer()
    warnings = _MessageBuffer()

    line_idx = 0
    for source_line in StringIO(text):
        raw_line = source_line.strip()
        if not raw_line:
            continue
        line_idx += 1
        locator = f"line:{line_idx}"
        clean = re.sub(r"^[-*+•\d.]+\s*", "", raw_line).strip()
        if not clean or clean.startswith("#"):
            continue

        match = re.match(r"^([A-Za-zÀ-ÿ0-9_\-\s]+?)\s*[:=]\s*(.+)$", clean)
        if not match:
            # Prose line in goals document: retain for review with explicit explanation
            if len(clean) >= 10:
                review_notes.append(
                    f"Prose retained for manual review: '{clean[:120]}' (goals do not generate career achievements)."
                )
            continue

        key_raw = match.group(1).strip().lower()
        val_raw = match.group(2).strip()
        excerpt = clean[:1000]

        # Explicit allowlist of supported canonical fields
        if key_raw in {
            "target_roles",
            "target roles",
            "target role",
            "roles",
            "ruoli desiderati",
            "ruoli",
            "ruolo",
        }:
            roles = [r.strip() for r in re.split(r"[,;|]", val_raw) if r.strip()]
            if roles:
                _validate_and_add_candidate(
                    candidates, review_notes, "target_roles", roles, f"{locator}:preference:target_roles", excerpt
                )
        elif key_raw in {
            "preferred_locations",
            "preferred locations",
            "locations",
            "location",
            "luoghi preferiti",
            "sedi preferite",
            "città",
        }:
            locs = [loc.strip() for loc in re.split(r"[,;|]", val_raw) if loc.strip()]
            if locs:
                _validate_and_add_candidate(
                    candidates,
                    review_notes,
                    "preferred_locations",
                    locs,
                    f"{locator}:preference:preferred_locations",
                    excerpt,
                )
        elif key_raw in {
            "preferred_languages",
            "preferred languages",
            "languages",
            "language",
            "lingue preferite",
            "lingue",
        }:
            langs = [lang.strip() for lang in re.split(r"[,;|]", val_raw) if lang.strip()]
            if langs:
                _validate_and_add_candidate(
                    candidates,
                    review_notes,
                    "preferred_languages",
                    langs,
                    f"{locator}:preference:preferred_languages",
                    excerpt,
                )
        elif key_raw in {
            "preferred_work_modes",
            "preferred work modes",
            "work modes",
            "work mode",
            "modalità di lavoro",
            "work_modes",
        }:
            items = [item.strip().lower() for item in re.split(r"[,;|]", val_raw) if item.strip()]
            valid_modes = []
            for item in items:
                mapped = _WORK_MODE_MAP.get(item)
                if mapped and mapped not in valid_modes:
                    valid_modes.append(mapped)
                elif not mapped:
                    review_notes.append(
                        f"Unrecognized work mode '{item}' in '{clean[:120]}'; omitted from candidates."
                    )
            if valid_modes:
                _validate_and_add_candidate(
                    candidates,
                    review_notes,
                    "preferred_work_modes",
                    valid_modes,
                    f"{locator}:preference:preferred_work_modes",
                    excerpt,
                )
        elif key_raw in {
            "contract_types",
            "contract types",
            "contract type",
            "tipi di contratto",
            "tipo contratto",
        }:
            items = [item.strip().lower() for item in re.split(r"[,;|]", val_raw) if item.strip()]
            valid_types = []
            for item in items:
                mapped = _CONTRACT_TYPE_MAP.get(item)
                if mapped and mapped not in valid_types:
                    valid_types.append(mapped)
                elif not mapped:
                    review_notes.append(
                        f"Unrecognized contract type '{item}' in '{clean[:120]}'; omitted from candidates."
                    )
            if valid_types:
                _validate_and_add_candidate(
                    candidates,
                    review_notes,
                    "contract_types",
                    valid_types,
                    f"{locator}:preference:contract_types",
                    excerpt,
                )
        elif key_raw in {
            "workload_min",
            "workload min",
            "minimum workload",
            "carico minimo",
            "percentuale minima",
        }:
            val = _whole_integer(val_raw, unit_pattern=r"%|percent|per\s*cento")
            if val is not None:
                _validate_and_add_candidate(
                    candidates, review_notes, "workload_min", val, f"{locator}:preference:workload_min", excerpt
                )
            else:
                _unsupported_value(review_notes, "workload_min", val_raw, clean)
        elif key_raw in {
            "workload_max",
            "workload max",
            "maximum workload",
            "carico massimo",
            "percentuale massima",
        }:
            val = _whole_integer(val_raw, unit_pattern=r"%|percent|per\s*cento")
            if val is not None:
                _validate_and_add_candidate(
                    candidates, review_notes, "workload_max", val, f"{locator}:preference:workload_max", excerpt
                )
            else:
                _unsupported_value(review_notes, "workload_max", val_raw, clean)
        elif key_raw in {"workload", "carico di lavoro", "workload bounds", "workload_bounds"}:
            range_match = re.fullmatch(
                r"\s*(\d+)\s*%?\s*(?:-|–|\.\.|to|a)\s*(\d+)\s*%?\s*",
                val_raw,
                flags=re.IGNORECASE,
            )
            if range_match:
                min_val = int(range_match.group(1))
                max_val = int(range_match.group(2))
                _validate_and_add_candidate(
                    candidates,
                    review_notes,
                    "workload_min",
                    min_val,
                    f"{locator}:preference:workload_min",
                    excerpt,
                )
                _validate_and_add_candidate(
                    candidates,
                    review_notes,
                    "workload_max",
                    max_val,
                    f"{locator}:preference:workload_max",
                    excerpt,
                )
            else:
                val = _whole_integer(val_raw, unit_pattern=r"%|percent|per\s*cento")
                if val is not None:
                    _validate_and_add_candidate(
                        candidates,
                        review_notes,
                        "workload_min",
                        val,
                        f"{locator}:preference:workload_min",
                        excerpt,
                    )
                    _validate_and_add_candidate(
                        candidates,
                        review_notes,
                        "workload_max",
                        val,
                        f"{locator}:preference:workload_max",
                        excerpt,
                    )
                else:
                    _unsupported_value(review_notes, "workload", val_raw, clean)
        elif key_raw in {"remote_only", "remote only", "solo da remoto", "solo remoto"}:
            val_lower = val_raw.lower()
            if val_lower in {"true", "yes", "si", "sì", "1"}:
                _validate_and_add_candidate(
                    candidates,
                    review_notes,
                    "remote_only",
                    True,
                    f"{locator}:preference:remote_only",
                    excerpt,
                )
            elif val_lower in {"false", "no", "0"}:
                _validate_and_add_candidate(
                    candidates,
                    review_notes,
                    "remote_only",
                    False,
                    f"{locator}:preference:remote_only",
                    excerpt,
                )
            else:
                review_notes.append(
                    f"Unrecognized boolean value '{val_raw}' for remote_only in '{clean[:120]}'."
                )
        elif key_raw in {
            "hard_max_distance_km",
            "max_distance_km",
            "maximum commute distance",
            "max commute distance",
            "distanza massima pendolare",
            "distanza massima",
            "max distance",
        }:
            dist_val = _whole_distance(val_raw)
            if dist_val is not None:
                _validate_and_add_candidate(
                    candidates,
                    review_notes,
                    "hard_max_distance_km",
                    dist_val,
                    f"{locator}:preference:hard_max_distance_km",
                    excerpt,
                )
            else:
                _unsupported_value(review_notes, "hard_max_distance_km", val_raw, clean)
        elif key_raw in {
            "available_from",
            "available from",
            "disponibile da",
            "data di disponibilità",
        }:
            iso_match = re.fullmatch(r"\d{4}-\d{2}-\d{2}", val_raw)
            if iso_match:
                try:
                    d = date.fromisoformat(iso_match.group(0))
                    _validate_and_add_candidate(
                        candidates,
                        review_notes,
                        "available_from",
                        d.isoformat(),
                        f"{locator}:preference:available_from",
                        excerpt,
                    )
                except ValueError:
                    review_notes.append(
                        f"Invalid date value '{val_raw}' for available_from in '{clean[:120]}'."
                    )
            else:
                review_notes.append(
                    f"Unsupported date format in '{clean[:120]}'; ISO YYYY-MM-DD expected."
                )
        elif key_raw in {
            "notice_period_days",
            "notice period days",
            "notice period",
            "giorni di preavviso",
            "preavviso",
        }:
            val = _whole_integer(val_raw, unit_pattern=r"days?|giorni")
            if val is not None:
                _validate_and_add_candidate(
                    candidates,
                    review_notes,
                    "notice_period_days",
                    val,
                    f"{locator}:preference:notice_period_days",
                    excerpt,
                )
            else:
                _unsupported_value(review_notes, "notice_period_days", val_raw, clean)
        else:
            # Unrecognized / unknown preference key or consent / credential
            review_notes.append(
                f"Unsupported preference key '{match.group(1).strip()}' in '{clean[:120]}'; field was not imported."
            )

    # Check cross-field combinations among all parsed candidates
    combined: dict[str, Any] = {}
    scalar_values: dict[str, set[str]] = {}
    for cand in candidates:
        combined[cand.field] = cand.value
        if not isinstance(cand.value, list):
            scalar_values.setdefault(cand.field, set()).add(
                json.dumps(cand.value, sort_keys=True, default=str)
            )
    for field, values in scalar_values.items():
        if len(values) > 1:
            warnings.append(
                f"Conflicting scalar candidates for {field}; choose exactly one value before applying."
            )
    if combined:
        try:
            CareerPreferences.model_validate(combined)
        except Exception as exc:
            warnings.append(
                f"Conflicting preference combination detected in source: {exc}. Review selections manually."
            )

    if candidates.omitted:
        review_notes.append(
            f"Candidate limit reached: {candidates.omitted} additional preference candidate(s) omitted."
        )

    return (
        list(candidates),
        review_notes.bounded(label="review notes"),
        warnings.bounded(label="warnings"),
    )


def _validate_and_add_candidate(
    candidates: _CandidateBuffer,
    review_notes: _MessageBuffer,
    field: PreferenceField,
    value: Any,
    locator: str,
    excerpt: str,
) -> None:
    try:
        CareerPreferences.model_validate({field: value})
        cand_id = _preference_candidate_id(locator, field, value)
        candidates.append(
            PreferenceCandidate(
                candidate_id=cand_id,
                field=field,
                value=value,
                source_locator=locator,
                excerpt=excerpt,
            )
        )
    except Exception as exc:
        review_notes.append(
            f"Invalid preference value for '{field}': {value!r} failed validation ({exc})."
        )
