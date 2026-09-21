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
