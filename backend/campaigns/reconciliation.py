"""Deterministic reconciliation and artifact classification for campaign workspace."""

from __future__ import annotations

from backend.campaigns.schemas import CampaignArtifactCategory


def reconcile_dossier_directory_name(dir_name: str, tracker_ids: set[str]) -> str:
    """Reconcile a packet directory name to its source application ID per FR-012/D11.

    1. Exact match first: if dir_name exactly matches a tracker ID, return it.
    2. Otherwise, match by the longest tracker ID followed by '_'.
    3. If no tracker ID matches, return dir_name unchanged (dossier-only).
    """
    if dir_name in tracker_ids:
        return dir_name
    candidates = [tid for tid in tracker_ids if dir_name.startswith(f"{tid}_")]
    if candidates:
        return max(candidates, key=len)
    return dir_name


def classify_artifact_category(canonical_path: str) -> CampaignArtifactCategory:
    """Classify archive member into canonical artifact category."""
    lower = canonical_path.lower()
    if lower == "applicationtracker.xlsx":
        return "tracker"
    if lower == "profile.md":
        return "profile"
    if lower == "goal.md":
        return "goal"
    if lower == "storytelling.md":
        return "story"
    if lower.endswith(".pdf") and "/" not in lower:
        return "evidence"
    if lower.startswith("scripts/"):
        return "script"
    if any(
        lower.startswith(p)
        for p in ("cv-templates/", "cover-letter-templates/", "email-templates/", "html-templates/")
    ):
        return "template"
    if lower.startswith("assets/"):
        if any(lower.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".svg")):
            return "image"
        return "evidence"
    if lower.startswith("application-packets/"):
        filename = lower.split("/")[-1]
        if filename == "vacancy.md":
            return "vacancy"
        if any(tok in filename for tok in ("cv", "resume")):
            return "cv"
        if any(tok in filename for tok in ("letter", "cover")):
            return "letter"
        if any(tok in filename for tok in ("email", "mail")):
            return "email"
        return "evidence"
    return "other"
