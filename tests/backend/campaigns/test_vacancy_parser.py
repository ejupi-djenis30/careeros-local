"""Tests for deterministic markdown vacancy parsing."""

from __future__ import annotations

from backend.campaigns.vacancy_parser import parse_vacancy_markdown


def test_parse_vacancy_markdown_standard_pattern():
    content = (
        "# Senior Cloud Architect\n\n"
        "**Company:** Fictional Cloud AG\n"
        "**Location:** Zurich, Switzerland\n"
        "**Category:** Cloud Engineering\n"
        "**URL:** https://example.com/jobs/123\n\n"
        "## Responsibilities\n"
        "- Build resilient architectures.\n"
    )
    result = parse_vacancy_markdown(content)
    assert result.title == "Senior Cloud Architect"
    assert result.company == "Fictional Cloud AG"
    assert result.location == "Zurich, Switzerland"
    assert result.category == "Cloud Engineering"
    assert result.url == "https://example.com/jobs/123"


def test_parse_vacancy_markdown_alternative_formatting():
    content = (
        "Role: Staff Engineer\n"
        "Company: Acme Systems\n"
        "Location: Remote\n"
        "[Posting Link](https://careers.example.com/staff)\n"
    )
    result = parse_vacancy_markdown(content)
    assert result.title == "Staff Engineer"
    assert result.company == "Acme Systems"
    assert result.location == "Remote"
    assert result.url == "https://careers.example.com/staff"


def test_parse_vacancy_markdown_defaults_without_inventing_evidence():
    content = "Some plain job posting notes without clear structure."
    result = parse_vacancy_markdown(content)
    assert result.title == "Untitled role"
    assert result.company == "Unknown company"
    assert result.location is None
    assert result.url is None
    assert result.category is None


def test_parse_bulleted_metadata_under_placeholder_heading():
    content = (
        "# Vacancy record — APP-20260911-001\n\n"
        "- **Company:** Fictional Foods AG\n"
        "- **Role:** Production employee, night shift\n"
        "- **Vacancy URL:** https://jobs.example.org/night-shift\n"
        "- **Location:** Zurich\n"
        "- **Category:** Production\n"
    )
    result = parse_vacancy_markdown(content)
    assert result.title == "Production employee, night shift"
    assert result.company == "Fictional Foods AG"
    assert result.location == "Zurich"
    assert result.category == "Production"
    assert result.url == "https://jobs.example.org/night-shift"


def test_parse_regular_worksite_from_dossier_metadata():
    content = (
        "# Backend Software Engineer\n\n"
        "- **Company:** Fictional Grid AG\n"
        "- **Regular worksite:** Brugg, Aargau\n"
    )
    result = parse_vacancy_markdown(content)
    assert result.location == "Brugg, Aargau"
