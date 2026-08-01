from __future__ import annotations

from scripts.check_release_versions import ROOT


def test_v1_10_release_evidence_records_the_immutable_publication() -> None:
    evidence = (ROOT / "docs" / "release-evidence-v1.10.0.md").read_text(encoding="utf-8")

    for expected in (
        "# CareerOS Local v1.10.0 release evidence",
        "Status: published.",
        "6fa804e7925e1d1420bd3f3f56e10cee0d3ea637",
        "fd98fb28ffe8eed6c5c69b37c8329f54d97a5eae",
        "2405d3aa0ea752b4bf2a18c55e605ae83610212b",
        "exactly 25 non-empty assets",
        "2b083973ca037e708df6f1738193f6d0cf8c99d8364a8d1f59aa7877ae21f20a",
        "a4587efc66f799893186eb8e8541392082033ef06de024b73300e98e604f9de7",
    ):
        assert expected in evidence

    for stale_claim in ("not been tagged", "not created", "| Pending |", "## Publication gates"):
        assert stale_claim not in evidence


def test_v1_9_release_evidence_no_longer_describes_a_pending_candidate() -> None:
    evidence = (ROOT / "docs" / "release-evidence-v1.9.0.md").read_text(encoding="utf-8")

    assert "# CareerOS Local v1.9.0 release evidence" in evidence
    assert "Status: published." in evidence
    assert "d1c1bdde076af0bea096c772684c1d9b47c14ed6" in evidence
    assert "final and immutable with 23 assets" in evidence
    assert "## Publication outcome" in evidence
    assert "## Publication gates" not in evidence
