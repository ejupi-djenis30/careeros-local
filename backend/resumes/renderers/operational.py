"""Compatibility entry points for the compact Swiss operational layout."""

from backend.resumes.renderers.semantic_layout import render_swiss_docx, render_swiss_pdf


def render_operational_pdf(snapshot: dict, photo: bytes | None = None) -> bytes:
    return render_swiss_pdf(snapshot, photo, operational=True)


def render_operational_docx(snapshot: dict, photo: bytes | None = None) -> bytes:
    return render_swiss_docx(snapshot, photo, operational=True)
