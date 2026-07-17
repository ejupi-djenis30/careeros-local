from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.career.models import CandidateProfile, CareerAsset, CareerFact
from backend.resumes.content import build_content
from backend.resumes.models import ResumeArtifact, ResumeDraft, ResumeVersion
from backend.resumes.quality import validate_resume_artifacts
from backend.resumes.renderers.ats import render_ats_docx, render_ats_pdf
from backend.resumes.renderers.base import DOCX_MEDIA_TYPE, PDF_MEDIA_TYPE
from backend.resumes.renderers.photo import render_photo_docx, render_photo_pdf
from backend.resumes.storage import remove_stored_artifact, store_resume_artifact

RENDERER_VERSION = "careeros-canvas-3.0"


def _snapshot(
    profile: CandidateProfile,
    draft: ResumeDraft,
    facts: list[CareerFact],
    photo: CareerAsset | None,
) -> dict:
    return {
        "schema_version": 3,
        "profile_revision": profile.revision,
        "profile": {
            "display_name": profile.display_name,
            "headline": profile.headline,
            "summary": profile.summary,
            "email": profile.email,
            "phone": profile.phone,
            "location": profile.location,
            "website": profile.website,
            "linkedin": profile.linkedin,
            "github": profile.github,
        },
        "resume": {
            "title": draft.title,
            "template_kind": draft.template_kind,
            "section_config": draft.section_config,
            "content_overrides": draft.content_overrides,
            "canvas_document": draft.canvas_document,
            "generation_context": draft.generation_context,
        },
        "selected_fact_ids": list(draft.selected_fact_ids),
        "facts": [
            {
                "id": fact.id,
                "fact_type": fact.fact_type,
                "position": fact.position,
                "payload": fact.payload,
                "verification_status": fact.verification_status,
                "source_document_id": fact.source_document_id,
            }
            for fact in facts
        ],
        "photo": {"asset_id": photo.id, "sha256": photo.sha256} if photo else None,
    }


def publish_draft(
    db: Session,
    *,
    profile: CandidateProfile,
    draft: ResumeDraft,
    facts: list[CareerFact],
    photo: CareerAsset | None,
    photo_bytes: bytes | None,
    version_name: str | None = None,
) -> ResumeVersion:
    snapshot = _snapshot(profile, draft, facts, photo)
    snapshot_json = json.dumps(
        snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    snapshot_sha256 = hashlib.sha256(snapshot_json).hexdigest()
    if draft.template_kind == "ats":
        pdf, docx = render_ats_pdf(snapshot), render_ats_docx(snapshot)
    else:
        pdf, docx = render_photo_pdf(snapshot, photo_bytes), render_photo_docx(
            snapshot, photo_bytes
        )
    content = build_content(snapshot)
    quality = validate_resume_artifacts(
        pdf=pdf,
        docx=docx,
        required_headings=content.required_headings,
        required_text=[
            content.display_name,
            *(entry.title for section in content.sections for entry in section.entries),
        ],
        template_kind=draft.template_kind,
        expect_photo=photo_bytes is not None,
        columns=int((draft.canvas_document or {}).get("style", {}).get("columns", 1)),
    )
    next_number = (
        int(
            db.query(func.coalesce(func.max(ResumeVersion.version_number), 0))
            .filter(ResumeVersion.draft_id == draft.id)
            .scalar()
        )
        + 1
    )
    published_at = datetime.now(timezone.utc)
    version = ResumeVersion(
        draft_id=draft.id,
        version_number=next_number,
        semantic_version=f"1.0.{next_number - 1}",
        name=(version_name or f"{draft.title} · v1.0.{next_number - 1}").strip()[:200],
        snapshot=snapshot,
        snapshot_sha256=snapshot_sha256,
        profile_revision=profile.revision,
        selected_fact_ids=list(draft.selected_fact_ids),
        template_kind=draft.template_kind,
        renderer_version=RENDERER_VERSION,
        published_at=published_at,
        quality_report=quality,
    )
    db.add(version)
    db.flush()
    stored_paths: list[str] = []
    try:
        for artifact_format, artifact_data, media_type in (
            ("pdf", pdf, PDF_MEDIA_TYPE),
            ("docx", docx, DOCX_MEDIA_TYPE),
        ):
            stored = store_resume_artifact(
                profile_id=profile.id,
                version_id=version.id,
                format=artifact_format,
                data=artifact_data,
            )
            if stored.created:
                stored_paths.append(stored.relative_path)
            db.add(
                ResumeArtifact(
                    version_id=version.id,
                    format=artifact_format,
                    media_type=media_type,
                    sha256=stored.sha256,
                    byte_size=stored.byte_size,
                    storage_path=stored.relative_path,
                    created_at=published_at,
                )
            )
        db.commit()
    except Exception:
        db.rollback()
        for path in stored_paths:
            remove_stored_artifact(path)
        raise
    db.expire_all()
    return db.query(ResumeVersion).filter(ResumeVersion.id == version.id).one()
