from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from backend.career.models import CandidateProfile, CareerAsset, CareerFact
from backend.resumes.content import build_content
from backend.resumes.exceptions import ResumeConflictError
from backend.resumes.models import ResumeArtifact, ResumeDraft, ResumeVersion
from backend.resumes.quality import validate_resume_artifacts
from backend.resumes.renderers.ats import render_ats_docx, render_ats_pdf
from backend.resumes.renderers.base import DOCX_MEDIA_TYPE, PDF_MEDIA_TYPE
from backend.resumes.renderers.photo import render_photo_docx, render_photo_pdf
from backend.resumes.storage import (
    is_resume_delete_pending,
    reconcile_resume_publication_journals,
    remove_resume_publication_journal,
    remove_stored_artifact,
    resume_artifact_path,
    store_resume_artifact,
    write_resume_publication_journal,
)

# Persist an artifact-format revision independently from the canvas schema.  The
# 3.0.1 renderer canonicalizes PDF/DOCX metadata and ZIP containers, so keeping
# the previous value would make byte-different publications indistinguishable in
# readiness exports and audit evidence.
RENDERER_VERSION = "careeros-canvas-3.0.1"


def _lock_publish_state(
    db: Session,
    *,
    draft_id: str,
    profile_id: str,
    expected_draft_revision: int,
    expected_profile_revision: int,
    normalized_canvas: dict,
) -> tuple[ResumeDraft, CandidateProfile]:
    """Revalidate the rendered snapshot while serializing version allocation."""

    sqlite = db.get_bind().dialect.name == "sqlite"
    if sqlite:
        # Request authentication and rendering establish a read snapshot. End it
        # before reserving the SQLite writer so BEGIN IMMEDIATE can wait instead
        # of failing a stale read-to-write upgrade with SQLITE_BUSY_SNAPSHOT.
        db.rollback()
        db.execute(sql_text("BEGIN IMMEDIATE"))

    draft_query = db.query(ResumeDraft).filter(ResumeDraft.id == draft_id)
    profile_query = db.query(CandidateProfile).filter(CandidateProfile.id == profile_id)
    if not sqlite:
        draft_query = draft_query.with_for_update()
        profile_query = profile_query.with_for_update()
    locked_draft = draft_query.populate_existing().one_or_none()
    locked_profile = profile_query.populate_existing().one_or_none()
    if (
        locked_draft is None
        or locked_profile is None
        or locked_draft.profile_id != profile_id
        or locked_draft.revision != expected_draft_revision
        or locked_profile.revision != expected_profile_revision
        or is_resume_delete_pending(locked_draft.generation_context)
    ):
        db.rollback()
        raise ResumeConflictError(
            "The resume or career profile changed while publishing. Review it and retry."
        )
    committed_version_ids = {
        version_id
        for (version_id,) in db.query(ResumeVersion.id)
        .filter(ResumeVersion.draft_id == draft_id)
        .all()
    }
    reconcile_resume_publication_journals(
        draft_id=draft_id,
        committed_version_ids=committed_version_ids,
    )
    locked_draft.canvas_document = normalized_canvas
    return locked_draft, locked_profile


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
    draft_id = draft.id
    profile_id = profile.id
    expected_draft_revision = draft.revision
    expected_profile_revision = profile.revision
    snapshot = _snapshot(profile, draft, facts, photo)
    snapshot_json = json.dumps(
        snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    snapshot_sha256 = hashlib.sha256(snapshot_json).hexdigest()
    if draft.template_kind == "ats":
        pdf, docx = render_ats_pdf(snapshot), render_ats_docx(snapshot)
    else:
        pdf, docx = (
            render_photo_pdf(snapshot, photo_bytes),
            render_photo_docx(snapshot, photo_bytes),
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
    draft, profile = _lock_publish_state(
        db,
        draft_id=draft_id,
        profile_id=profile_id,
        expected_draft_revision=expected_draft_revision,
        expected_profile_revision=expected_profile_revision,
        normalized_canvas=snapshot["resume"]["canvas_document"],
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
    version_id = str(uuid.uuid4())
    version = ResumeVersion(
        id=version_id,
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
    expected_paths = [
        resume_artifact_path(
            profile_id=profile.id,
            version_id=version_id,
            format=artifact_format,
            sha256=hashlib.sha256(artifact_data).hexdigest(),
        )
        for artifact_format, artifact_data in (("pdf", pdf), ("docx", docx))
    ]
    journal_path: str | None = None
    try:
        db.add(version)
        db.flush()
        journal_path = write_resume_publication_journal(
            draft_id=draft.id,
            version_id=version_id,
            artifact_paths=expected_paths,
        )
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
    except Exception as publish_error:
        db.rollback()
        try:
            committed = (
                db.query(ResumeVersion.id).filter(ResumeVersion.id == version_id).scalar()
                is not None
            )
        except Exception:
            # Commit acknowledgement can be ambiguous. Preserve durable bytes
            # unless a fresh transaction proves that no row references them.
            db.rollback()
            raise publish_error
        if committed:
            if journal_path is not None:
                try:
                    remove_resume_publication_journal(journal_path)
                except Exception:
                    # The committed rows own the files. A later operation can
                    # safely discard the redundant recovery journal.
                    pass
        else:
            cleanup_error: Exception | None = None
            for path in expected_paths:
                try:
                    remove_stored_artifact(path)
                except Exception as error:
                    cleanup_error = cleanup_error or error
            if cleanup_error is None and journal_path is not None:
                try:
                    remove_resume_publication_journal(journal_path)
                except Exception as error:
                    cleanup_error = error
            if cleanup_error is not None:
                raise cleanup_error from publish_error
            raise publish_error
    else:
        if journal_path is not None:
            try:
                remove_resume_publication_journal(journal_path)
            except Exception:
                # The committed DB rows are authoritative; retain the journal
                # for deterministic reconciliation by the next locked action.
                pass
    db.expire_all()
    return db.query(ResumeVersion).filter(ResumeVersion.id == version_id).one()
