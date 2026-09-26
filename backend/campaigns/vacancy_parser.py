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


def _labeled_value(lines: list[str], names: set[str]) -> str | None:
    """Read explicit Markdown metadata, including list bullets and bold labels."""
    for line in lines:
        line = re.sub(r"^[-*+]\s+", "", line)
        label, separator, value = line.partition(":")
        if not separator or label.strip(" *").casefold() not in names:
            continue
        clean = value.strip(" *").strip()
        if clean:
            return clean
    return None


def parse_vacancy_markdown(text: str) -> ParsedVacancy:
    lines = [line.strip() for line in text.splitlines()]

    title: str | None = None
    company: str | None = None
    location: str | None = None
    url: str | None = None
    category: str | None = None

    # A real H1 is authoritative, but imported packet placeholders carry only an ID.
    for line in lines:
        if line.startswith("# ") and not line.startswith("##"):
            title = line[2:].strip()
            title = re.sub(r"^\[|\]$", "", title).strip()
            break
    explicit_title = _labeled_value(lines, {"role", "job title", "title", "posizione"})
    if not title or re.fullmatch(r"Vacancy record\s*[-–—]\s*APP-[A-Za-z0-9-]+", title, re.I):
        title = explicit_title or title

    company = _labeled_value(lines, {"company", "azienda", "employer"})
    location = _labeled_value(
        lines, {"location", "regular worksite", "luogo", "sede", "city"}
    )
    category = _labeled_value(lines, {"category", "job category", "categoria"})
    url = _labeled_value(
        lines, {"url", "job url", "vacancy url", "posting url", "application url", "link"}
    )
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
