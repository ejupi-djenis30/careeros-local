from backend.resumes.renderers.base import render_docx, render_pdf


def render_ats_pdf(snapshot: dict) -> bytes:
    return render_pdf(snapshot)


def render_ats_docx(snapshot: dict) -> bytes:
    return render_docx(snapshot)
