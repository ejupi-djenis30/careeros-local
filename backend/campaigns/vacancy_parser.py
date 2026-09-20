"""Deterministic parser for dossier-only vacancy.md references."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ParsedVacancy:
    title: str
    company: str
    location: str | None
    url: str | None
    category: str | None
    raw_markdown: str


def _clean_match(m: re.Match | None) -> str | None:
    if not m:
        return None
    val = m.group(1).strip()
    # Strip markdown brackets or bold markers
    val = re.sub(r"^\*+|\*+$", "", val).strip()
    val = re.sub(r"^\[|\]$", "", val).strip()
    return val or None


def parse_vacancy_markdown(text: str) -> ParsedVacancy:
    lines = [line.strip() for line in text.splitlines()]

    title: str | None = None
    company: str | None = None
    location: str | None = None
    url: str | None = None
    category: str | None = None

    # Title heuristics: H1 header first, then Role / Title prefixes
    for line in lines:
        if line.startswith("# ") and not line.startswith("##"):
            title = line[2:].strip()
            title = re.sub(r"^\[|\]$", "", title).strip()
            break
    if not title:
        m = re.search(r"^(?:\*\*|\*|)?(?:Role|Job Title|Title|Posizione)(?:\*\*|\*|)?\s*:\s*(.+)$", text, re.M | re.I)
        title = _clean_match(m)

    m = re.search(r"^(?:\*\*|\*|)?(?:Company|Azienda|Employer)(?:\*\*|\*|)?\s*:\s*(.+)$", text, re.M | re.I)
    company = _clean_match(m)

    m = re.search(r"^(?:\*\*|\*|)?(?:Location|Luogo|Sede|City)(?:\*\*|\*|)?\s*:\s*(.+)$", text, re.M | re.I)
    location = _clean_match(m)

    m = re.search(r"^(?:\*\*|\*|)?(?:Category|Job Category|Categoria)(?:\*\*|\*|)?\s*:\s*(.+)$", text, re.M | re.I)
    category = _clean_match(m)

    m = re.search(r"^(?:\*\*|\*|)?(?:URL|Job URL|Link|Application URL)(?:\*\*|\*|)?\s*:\s*(.+)$", text, re.M | re.I)
    url = _clean_match(m)
    if not url:
        # Check for markdown link [Label](https://...)
        m_link = re.search(r"\[.*?\]\((https?://[^\s\)]+)\)", text, re.I)
        if m_link:
            url = m_link.group(1).strip()

    return ParsedVacancy(
        title=title or "Untitled role",
        company=company or "Unknown company",
        location=location,
        url=url,
        category=category,
        raw_markdown=text,
    )
