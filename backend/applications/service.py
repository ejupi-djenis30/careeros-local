import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.applications.models import Application, ApplicationEvent
from backend.applications.schemas import (
    ApplicationCreate,
    ApplicationEventCreate,
    ApplicationResponse,
    ApplicationSummary,
)
from backend.models import Job, ScrapedJob
from backend.resumes.models import ResumeDraft, ResumeVersion

TRANSITIONS = {
    "saved": {"preparing", "applied", "withdrawn", "archived"},
    "preparing": {"saved", "applied", "withdrawn", "archived"},
    "applied": {"screening", "interview", "rejected", "withdrawn", "archived"},
    "screening": {"interview", "offer", "rejected", "withdrawn", "archived"},
    "interview": {"interview", "offer", "rejected", "withdrawn", "archived"},
    "offer": {"accepted", "rejected", "withdrawn", "archived"},
    "accepted": {"archived"},
    "rejected": {"archived"},
    "withdrawn": {"archived"},
    "archived": set(),
}


class ApplicationNotFoundError(LookupError):
    pass


class ApplicationConflictError(RuntimeError):
    pass


class ApplicationValidationError(ValueError):
    pass


class ApplicationService:
    def __init__(self, db: Session):
        self.db = db

    def _application(self, user_id: int, application_id: str) -> Application:
        application = (
            self.db.query(Application)
            .filter(Application.id == application_id, Application.user_id == user_id)
            .first()
        )
        if application is None:
            raise ApplicationNotFoundError("Application not found")
        return application

    def _resume_version(self, user_id: int, version_id: str | None) -> ResumeVersion | None:
        if version_id is None:
            return None
        version = (
            self.db.query(ResumeVersion)
            .join(ResumeDraft, ResumeVersion.draft_id == ResumeDraft.id)
            .filter(ResumeVersion.id == version_id)
            .first()
        )
        if version is None or version.draft.profile_id is None:
            raise ApplicationValidationError("Resume version not found")
        from backend.career.models import CandidateProfile

        owns_version = (
            self.db.query(CandidateProfile.id)
            .filter(
                CandidateProfile.id == version.draft.profile_id, CandidateProfile.user_id == user_id
            )
            .first()
        )
        if owns_version is None:
            raise ApplicationValidationError("Resume version not found")
        return version

    @staticmethod
    def _snapshot(job: Job) -> dict:
        scraped: ScrapedJob = job.scraped_job
        return {
            "schema_version": 1,
            "job_id": job.id,
            "scraped_job_id": scraped.id,
            "title": scraped.title,
            "company": scraped.company,
            "description": scraped.description,
            "location": scraped.location,
            "external_url": scraped.external_url,
            "application_url": scraped.application_url,
            "application_email": scraped.application_email,
            "workload": scraped.workload,
            "publication_date": (
                scraped.publication_date.isoformat() if scraped.publication_date else None
            ),
            "platform": scraped.platform,
            "platform_job_id": scraped.platform_job_id,
            "source_query": scraped.source_query,
            "raw_metadata": scraped.raw_metadata,
            "normalized": json.loads(json.dumps(scraped.normalized_job_data, default=str)),
            "match": {
                "score": job.affinity_score,
                "analysis": job.affinity_analysis,
                "worth_applying": job.worth_applying,
            },
        }

    @staticmethod
    def _manual_snapshot(data) -> dict:
        return {
            "schema_version": 1,
            "job_id": None,
            "scraped_job_id": None,
            "title": data.title,
            "company": data.company,
            "description": data.description,
            "location": data.location,
            "external_url": data.external_url,
            "application_url": data.application_url,
            "application_email": data.application_email,
            "workload": data.workload,
            "publication_date": None,
            "platform": "manual",
            "platform_job_id": None,
            "source_query": None,
            "raw_metadata": {"source": "manual"},
            "normalized": {},
            "match": {
                "score": None,
                "analysis": "Manually captured local job snapshot",
                "worth_applying": None,
            },
        }

    def create(self, user_id: int, data: ApplicationCreate) -> ApplicationResponse:
        job = None
        if data.job_id is not None:
            job = self.db.query(Job).filter(Job.id == data.job_id, Job.user_id == user_id).first()
            if job is None:
                raise ApplicationValidationError("Job not found")
        self._resume_version(user_id, data.resume_version_id)
        if job is not None:
            existing = (
                self.db.query(Application)
                .filter(Application.user_id == user_id, Application.job_id == job.id)
                .first()
            )
            if existing is not None:
                raise ApplicationConflictError("An application already exists for this job")
            snapshot = self._snapshot(job)
        else:
            if data.manual_job is None:  # Schema validation guarantees this; keep the service safe.
                raise ApplicationValidationError("Manual job snapshot is required")
            snapshot = self._manual_snapshot(data.manual_job)
        now = datetime.now(timezone.utc)
        application = Application(
            user_id=user_id,
            job_id=job.id if job is not None else None,
            resume_version_id=data.resume_version_id,
            revision=1,
            current_stage=data.initial_stage,
            job_snapshot=snapshot,
        )
        self.db.add(application)
        self.db.flush()
        self.db.add(
            ApplicationEvent(
                application_id=application.id,
                event_type="stage",
                stage=data.initial_stage,
                occurred_at=now,
                note=data.note,
                payload={"initial": True},
                created_at=now,
            )
        )
        self.db.commit()
        self.db.expire_all()
        return ApplicationResponse.model_validate(self._application(user_id, application.id))

    def append_event(
        self, user_id: int, application_id: str, data: ApplicationEventCreate
    ) -> ApplicationResponse:
        application = self._application(user_id, application_id)
        if application.revision != data.expected_revision:
            raise ApplicationConflictError(
                f"Expected revision {data.expected_revision}, current revision is "
                f"{application.revision}"
            )
        if data.event_type == "stage" and data.stage != application.current_stage:
            allowed = TRANSITIONS[application.current_stage]
            if data.stage not in allowed:
                raise ApplicationConflictError(
                    f"Cannot transition from {application.current_stage} to {data.stage}"
                )
            application.current_stage = data.stage
        now = datetime.now(timezone.utc)
        event = ApplicationEvent(
            application_id=application.id,
            event_type=data.event_type,
            stage=data.stage,
            occurred_at=data.occurred_at or now,
            note=data.note,
            payload=data.payload,
            created_at=now,
        )
        self.db.add(event)
        application.revision += 1
        self.db.commit()
        self.db.expire_all()
        return ApplicationResponse.model_validate(self._application(user_id, application_id))

    def get(self, user_id: int, application_id: str) -> ApplicationResponse:
        return ApplicationResponse.model_validate(self._application(user_id, application_id))

    def list(
        self, user_id: int, *, offset: int = 0, limit: int = 200
    ) -> list[ApplicationSummary]:
        applications = (
            self.db.query(Application)
            .filter(Application.user_id == user_id)
            .order_by(Application.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [
            ApplicationSummary(
                id=item.id,
                job_id=item.job_id,
                resume_version_id=item.resume_version_id,
                revision=item.revision,
                current_stage=item.current_stage,
                title=str(item.job_snapshot.get("title") or "Untitled role"),
                company=str(item.job_snapshot.get("company") or "Unknown company"),
                location=item.job_snapshot.get("location"),
                latest_event_at=item.events[-1].occurred_at,
                updated_at=item.updated_at,
            )
            for item in applications
        ]
