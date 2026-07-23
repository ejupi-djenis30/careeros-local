import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Literal, cast

from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.applications.exports import (
    MAX_DOSSIER_ARTIFACT_BYTES,
    MAX_DOSSIER_EVENT_BYTES,
    DossierBundle,
    DossierSizeError,
    build_dossier_bundle,
    canonical_json,
    export_task_calendar,
)
from backend.applications.models import Application, ApplicationEvent
from backend.applications.readiness import ApplicationReadinessService
from backend.applications.readiness_export import ReadinessExport, export_readiness
from backend.applications.schemas import (
    ApplicationCreate,
    ApplicationDossierCreate,
    ApplicationDossierSummary,
    ApplicationEventCreate,
    ApplicationNextAction,
    ApplicationPreparationUpdate,
    ApplicationReadinessReport,
    ApplicationResponse,
    ApplicationSummary,
    ApplicationTaskCreate,
    ApplicationTaskPriority,
    ApplicationTaskResponse,
    ApplicationTaskUpdate,
)
from backend.applications.snapshots import (
    sanitize_application_snapshot,
    snapshot_from_job,
)
from backend.db.types import aware_utc
from backend.models import Job
from backend.resumes.models import ResumeDraft, ResumeVersion
from backend.storage.atomic import read_verified

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
    def _task_snapshots(application: Application) -> list[ApplicationTaskResponse]:
        histories: dict[str, dict[int, ApplicationTaskResponse]] = {}
        canonical_by_revision: dict[tuple[str, int], str] = {}
        task_event_types = {
            "task_created",
            "task_updated",
            "task_completed",
            "task_reopened",
            "task_cancelled",
        }
        for event in application.events:
            if event.event_type not in task_event_types or not isinstance(event.payload, dict):
                continue
            payload = event.payload.get("task")
            if not isinstance(payload, dict):
                continue
            try:
                task = ApplicationTaskResponse.model_validate(payload)
            except ValidationError as exc:
                raise ApplicationValidationError("Invalid task event payload") from exc
            if event.event_type == "task_created":
                if task.revision != 1 or task.status != "pending":
                    raise ApplicationValidationError("Invalid task creation event")
            elif task.revision <= 1:
                raise ApplicationValidationError("Task revision regressed")
            expected_status = {
                "task_completed": "completed",
                "task_reopened": "pending",
                "task_cancelled": "cancelled",
            }.get(event.event_type)
            if expected_status is not None and task.status != expected_status:
                raise ApplicationValidationError("Task event status is inconsistent")

            canonical = json.dumps(
                task.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            )
            revision_key = (task.id, task.revision)
            previous_canonical = canonical_by_revision.get(revision_key)
            if previous_canonical is not None and previous_canonical != canonical:
                raise ApplicationValidationError("Conflicting duplicate task revision")
            canonical_by_revision[revision_key] = canonical
            histories.setdefault(task.id, {})[task.revision] = task

        current: dict[str, ApplicationTaskResponse] = {}
        for task_id, revisions in histories.items():
            highest = max(revisions)
            if set(revisions) != set(range(1, highest + 1)):
                raise ApplicationValidationError("Task revision history is incomplete")
            ordered = [revisions[revision] for revision in range(1, highest + 1)]
            created_at = ordered[0].created_at
            previous_updated_at = ordered[0].updated_at
            for task in ordered[1:]:
                if task.created_at != created_at or task.updated_at < previous_updated_at:
                    raise ApplicationValidationError("Task revision history regressed")
                previous_updated_at = task.updated_at
            current[task_id] = ordered[-1]
        priority = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
        far_future = datetime.max.replace(tzinfo=timezone.utc)
        return sorted(
            current.values(),
            key=lambda task: (
                task.status != "pending",
                task.due_at or far_future,
                priority[task.priority],
                task.created_at,
                task.id,
            ),
        )

    @staticmethod
    def _dossier_summaries(application: Application) -> list[ApplicationDossierSummary]:
        summaries: list[ApplicationDossierSummary] = []
        for event in application.events:
            if event.event_type != "dossier_published" or not isinstance(event.payload, dict):
                continue
            dossier = event.payload.get("dossier")
            if not isinstance(dossier, dict):
                continue
            try:
                summaries.append(
                    ApplicationDossierSummary(
                        id=event.id,
                        version_number=dossier["version_number"],
                        application_revision=dossier["application_revision"],
                        resume_version_id=dossier["resume_version_id"],
                        created_at=dossier["created_at"],
                        manifest_sha256=dossier["manifest_sha256"],
                        readiness_fingerprint=dossier["readiness_fingerprint"],
                        requirement_count=len(dossier.get("requirement_matrix") or []),
                        completed_checklist=sum(
                            bool(item.get("completed"))
                            for item in dossier.get("checklist") or []
                            if isinstance(item, dict)
                        ),
                        checklist_total=len(dossier.get("checklist") or []),
                    )
                )
            except (KeyError, TypeError, ValidationError):
                continue
        return sorted(summaries, key=lambda item: item.version_number, reverse=True)

    def _safe_snapshot(self, application: Application) -> dict[str, Any]:
        verified_job = None
        if application.job_id is not None:
            job = self.db.get(Job, application.job_id)
            if job is not None and job.user_id == application.user_id:
                from backend.services.job_service import JobService

                verified_job = JobService(self.db)._mark_analysis_receipt(job, application.user_id)
        return sanitize_application_snapshot(
            application.job_snapshot,
            verified_job=verified_job,
            quarantine_reason="analysis_not_receipt_verified",
        )

    def _response(self, application: Application) -> ApplicationResponse:
        return ApplicationResponse.model_validate(application).model_copy(
            update={
                "job_snapshot": self._safe_snapshot(application),
                "tasks": self._task_snapshots(application),
                "dossiers": self._dossier_summaries(application),
            }
        )

    @staticmethod
    def _next_action(
        tasks: list[ApplicationTaskResponse],
    ) -> ApplicationTaskResponse | None:
        return next((task for task in tasks if task.status == "pending"), None)

    @staticmethod
    def _projection(next_action: ApplicationTaskResponse | None) -> dict:
        return {
            Application.next_action_task_id: next_action.id if next_action else None,
            Application.next_action_title: next_action.title if next_action else None,
            Application.next_action_at: next_action.due_at if next_action else None,
            Application.next_action_priority: next_action.priority if next_action else None,
        }

    @staticmethod
    def _projected_next_action(application: Application) -> ApplicationNextAction | None:
        task_id = application.next_action_task_id
        title = application.next_action_title
        priority = application.next_action_priority
        values = (task_id, title, priority)
        if all(value is None for value in values):
            return None
        if task_id is None or title is None or priority is None:
            raise ApplicationValidationError("Next-action projection is incomplete")
        return ApplicationNextAction(
            id=task_id,
            title=title,
            due_at=application.next_action_at,
            priority=cast(ApplicationTaskPriority, priority),
        )

    def _advance_revision(
        self,
        application: Application,
        expected_revision: int,
        now: datetime,
        values: dict | None = None,
    ) -> None:
        if application.revision != expected_revision:
            raise ApplicationConflictError(
                f"Expected revision {expected_revision}, current revision is {application.revision}"
            )
        projected_event_at = aware_utc(now)
        current_latest = aware_utc(application.latest_event_at)
        latest_event_at = max(
            value for value in (projected_event_at, current_latest) if value is not None
        )
        update_values = {
            Application.revision: expected_revision + 1,
            Application.updated_at: now,
            Application.latest_event_at: latest_event_at,
            **(values or {}),
        }
        updated = (
            self.db.query(Application)
            .filter(
                Application.id == application.id,
                Application.user_id == application.user_id,
                Application.revision == expected_revision,
            )
            .update(update_values, synchronize_session=False)
        )
        if updated != 1:
            self.db.rollback()
            raise ApplicationConflictError("Application changed in another session")

    @staticmethod
    def _snapshot(job: Job) -> dict:
        return snapshot_from_job(job)

    @staticmethod
    def _manual_snapshot(data) -> dict:
        snapshot = {
            "schema_version": 2,
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
            "match": {},
        }
        return sanitize_application_snapshot(
            snapshot,
            quarantine_reason="manual_snapshot_has_no_model_analysis",
        )

    def create(self, user_id: int, data: ApplicationCreate) -> ApplicationResponse:
        job = None
        if data.job_id is not None:
            job = self.db.query(Job).filter(Job.id == data.job_id, Job.user_id == user_id).first()
            if job is None:
                raise ApplicationValidationError("Job not found")
        resume_version_id = str(data.resume_version_id) if data.resume_version_id else None
        self._resume_version(user_id, resume_version_id)
        if job is not None:
            existing = (
                self.db.query(Application)
                .filter(Application.user_id == user_id, Application.job_id == job.id)
                .first()
            )
            if existing is not None:
                raise ApplicationConflictError("An application already exists for this job")
            from backend.services.job_service import JobService

            JobService(self.db)._mark_analysis_receipt(job, user_id)
            snapshot = self._snapshot(job)
        else:
            if data.manual_job is None:  # Schema validation guarantees this; keep the service safe.
                raise ApplicationValidationError("Manual job snapshot is required")
            snapshot = self._manual_snapshot(data.manual_job)
        now = datetime.now(timezone.utc)
        application = Application(
            user_id=user_id,
            job_id=job.id if job is not None else None,
            resume_version_id=resume_version_id,
            revision=1,
            current_stage=data.initial_stage,
            job_snapshot=snapshot,
            job_title=str(snapshot.get("title") or "Untitled role")[:240],
            job_company=str(snapshot.get("company") or "Unknown company")[:240],
            job_location=(
                str(snapshot["location"])[:500] if snapshot.get("location") is not None else None
            ),
            latest_event_at=now,
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
        return self._response(self._application(user_id, application.id))

    def append_event(
        self, user_id: int, application_id: str, data: ApplicationEventCreate
    ) -> ApplicationResponse:
        application = self._application(user_id, application_id)
        if application.revision != data.expected_revision:
            raise ApplicationConflictError(
                f"Expected revision {data.expected_revision}, current revision is "
                f"{application.revision}"
            )
        next_stage = application.current_stage
        if data.event_type == "stage" and data.stage != application.current_stage:
            allowed = TRANSITIONS[application.current_stage]
            if data.stage not in allowed:
                raise ApplicationConflictError(
                    f"Cannot transition from {application.current_stage} to {data.stage}"
                )
            next_stage = data.stage
        now = datetime.now(timezone.utc)
        event_at = data.occurred_at or now
        self._advance_revision(
            application,
            data.expected_revision,
            now,
            {
                Application.current_stage: next_stage,
                Application.latest_event_at: max(
                    aware_utc(application.latest_event_at) or event_at,
                    aware_utc(event_at) or now,
                ),
            },
        )
        event = ApplicationEvent(
            application_id=application.id,
            event_type=data.event_type,
            stage=data.stage,
            occurred_at=event_at,
            note=data.note,
            payload=data.payload,
            created_at=now,
        )
        self.db.add(event)
        self.db.commit()
        self.db.expire_all()
        return self._response(self._application(user_id, application_id))

    def get(self, user_id: int, application_id: str) -> ApplicationResponse:
        return self._response(self._application(user_id, application_id))

    def readiness(self, user_id: int, application_id: str) -> ApplicationReadinessReport:
        application = self._application(user_id, application_id)
        return ApplicationReadinessService(self.db).build(user_id, application)

    def export_readiness(
        self,
        user_id: int,
        application_id: str,
        export_format: Literal["json", "markdown"],
    ) -> ReadinessExport:
        return export_readiness(self.readiness(user_id, application_id), export_format)

    def update_preparation(
        self, user_id: int, application_id: str, data: ApplicationPreparationUpdate
    ) -> ApplicationResponse:
        application = self._application(user_id, application_id)
        if application.revision != data.expected_revision:
            raise ApplicationConflictError(
                f"Expected revision {data.expected_revision}, current revision is "
                f"{application.revision}"
            )

        changed_fields: list[str] = []
        snapshot = self._safe_snapshot(application)
        for field in (
            "title",
            "company",
            "description",
            "application_url",
            "application_email",
        ):
            if field not in data.model_fields_set:
                continue
            value = getattr(data, field)
            if snapshot.get(field) != value:
                snapshot[field] = value
                changed_fields.append(field)

        resume_version_id = application.resume_version_id
        if "resume_version_id" in data.model_fields_set:
            if data.resume_version_id is not None:
                self._resume_version(user_id, str(data.resume_version_id))
            next_resume_version_id = (
                str(data.resume_version_id) if data.resume_version_id is not None else None
            )
            if resume_version_id != next_resume_version_id:
                resume_version_id = next_resume_version_id
                changed_fields.append("resume_version_id")

        if not changed_fields:
            raise ApplicationValidationError("Application preparation is unchanged")

        now = datetime.now(timezone.utc)
        updated = (
            self.db.query(Application)
            .filter(
                Application.id == application_id,
                Application.user_id == user_id,
                Application.revision == data.expected_revision,
            )
            .update(
                {
                    Application.job_snapshot: snapshot,
                    Application.job_title: str(snapshot.get("title") or "Untitled role")[:240],
                    Application.job_company: str(snapshot.get("company") or "Unknown company")[
                        :240
                    ],
                    Application.job_location: (
                        str(snapshot["location"])[:500]
                        if snapshot.get("location") is not None
                        else None
                    ),
                    Application.resume_version_id: resume_version_id,
                    Application.revision: data.expected_revision + 1,
                    Application.updated_at: now,
                    Application.latest_event_at: max(
                        aware_utc(application.latest_event_at) or now,
                        now,
                    ),
                },
                synchronize_session=False,
            )
        )
        if updated != 1:
            self.db.rollback()
            raise ApplicationConflictError("Application changed during preparation update")
        self.db.add(
            ApplicationEvent(
                application_id=application_id,
                event_type="preparation",
                stage=None,
                occurred_at=now,
                note=None,
                payload={"changed_fields": sorted(changed_fields)},
                created_at=now,
            )
        )
        self.db.commit()
        self.db.expire_all()
        return self._response(self._application(user_id, application_id))

    def create_task(
        self, user_id: int, application_id: str, data: ApplicationTaskCreate
    ) -> ApplicationResponse:
        application = self._application(user_id, application_id)
        now = datetime.now(timezone.utc)
        task = ApplicationTaskResponse(
            id=str(uuid.uuid4()),
            title=data.title,
            status="pending",
            priority=data.priority,
            due_at=data.due_at,
            reminder_at=data.reminder_at,
            completed_at=None,
            revision=1,
            created_at=now,
            updated_at=now,
        )
        tasks = [*self._task_snapshots(application), task]
        self._advance_revision(
            application,
            data.expected_revision,
            now,
            self._projection(self._next_action(sorted(tasks, key=self._task_sort_key))),
        )
        self.db.add(
            ApplicationEvent(
                application_id=application_id,
                event_type="task_created",
                stage=None,
                occurred_at=now,
                note=task.title,
                payload={"schema_version": "1.0", "task": task.model_dump(mode="json")},
                created_at=now,
            )
        )
        self.db.commit()
        self.db.expire_all()
        return self._response(self._application(user_id, application_id))

    @staticmethod
    def _task_sort_key(task: ApplicationTaskResponse):
        priority = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
        return (
            task.status != "pending",
            task.due_at or datetime.max.replace(tzinfo=timezone.utc),
            priority[task.priority],
            task.created_at,
            task.id,
        )

    def update_task(
        self,
        user_id: int,
        application_id: str,
        task_id: str,
        data: ApplicationTaskUpdate,
    ) -> ApplicationResponse:
        application = self._application(user_id, application_id)
        tasks = self._task_snapshots(application)
        current = next((task for task in tasks if task.id == task_id), None)
        if current is None:
            raise ApplicationNotFoundError("Application task not found")
        updates: dict = {}
        for field in ("title", "due_at", "priority", "reminder_at", "status"):
            if field in data.model_fields_set:
                updates[field] = getattr(data, field)
        if updates.get("due_at", current.due_at) is None:
            updates["reminder_at"] = None
        final_due_at = updates.get("due_at", current.due_at)
        final_reminder_at = updates.get("reminder_at", current.reminder_at)
        if final_reminder_at is not None:
            if final_due_at is None:
                raise ApplicationValidationError("due_at is required when reminder_at is set")
            if final_reminder_at > final_due_at:
                raise ApplicationValidationError("reminder_at cannot be after due_at")
        now = datetime.now(timezone.utc)
        next_status = updates.get("status", current.status)
        if next_status == "completed" and current.status != "completed":
            updates["completed_at"] = now
        elif next_status != "completed" and current.status == "completed":
            updates["completed_at"] = None
        changed = any(getattr(current, key) != value for key, value in updates.items())
        if not changed:
            raise ApplicationValidationError("Application task is unchanged")
        updated_task = current.model_copy(
            update={**updates, "revision": current.revision + 1, "updated_at": now}
        )
        event_type = "task_updated"
        if current.status != updated_task.status:
            event_type = {
                "completed": "task_completed",
                "cancelled": "task_cancelled",
                "pending": "task_reopened",
            }[updated_task.status]
        next_tasks = [updated_task if task.id == task_id else task for task in tasks]
        next_tasks.sort(key=self._task_sort_key)
        self._advance_revision(
            application,
            data.expected_revision,
            now,
            self._projection(self._next_action(next_tasks)),
        )
        self.db.add(
            ApplicationEvent(
                application_id=application_id,
                event_type=event_type,
                stage=None,
                occurred_at=now,
                note=updated_task.title,
                payload={
                    "schema_version": "1.0",
                    "task": updated_task.model_dump(mode="json"),
                },
                created_at=now,
            )
        )
        self.db.commit()
        self.db.expire_all()
        return self._response(self._application(user_id, application_id))

    def task_calendar(self, user_id: int, application_id: str) -> bytes:
        application = self._application(user_id, application_id)
        snapshot = application.job_snapshot or {}
        return export_task_calendar(
            application.id,
            str(snapshot.get("title") or "Application"),
            str(snapshot.get("company") or "Unknown company"),
            self._task_snapshots(application),
        )

    @staticmethod
    def _verified_resume_artifacts(version: ResumeVersion) -> dict[str, tuple[bytes, str]]:
        artifacts: dict[str, tuple[bytes, str]] = {}
        for artifact in version.artifacts:
            if artifact.format not in {"pdf", "docx"}:
                continue
            if artifact.byte_size > MAX_DOSSIER_ARTIFACT_BYTES:
                raise ApplicationValidationError(
                    f"The stored {artifact.format.upper()} resume artifact exceeds the dossier limit"
                )
            try:
                data = read_verified(artifact.storage_path, artifact.sha256)
            except (OSError, ValueError) as exc:
                raise ApplicationValidationError(
                    f"The stored {artifact.format.upper()} resume artifact failed verification"
                ) from exc
            if len(data) != artifact.byte_size:
                raise ApplicationValidationError("Resume artifact size does not match its record")
            artifacts[artifact.format] = (data, artifact.media_type)
        if not artifacts:
            raise ApplicationValidationError("The linked resume has no verified export artifact")
        return artifacts

    def _bundle_from_dossier(
        self,
        user_id: int,
        application: Application,
        dossier_id: str,
        dossier: dict,
    ) -> DossierBundle:
        version = self._resume_version(user_id, dossier.get("resume_version_id"))
        if version is None:
            raise ApplicationValidationError("The dossier resume version is unavailable")
        try:
            bundle = build_dossier_bundle(
                dossier_id=dossier_id,
                version_number=dossier["version_number"],
                application_revision=dossier["application_revision"],
                application_id=application.id,
                created_at=dossier["created_at"],
                role=dossier["role"],
                resume_version_id=version.id,
                readiness=dossier["readiness"],
                cover_letter=dossier.get("cover_letter"),
                answers=dossier.get("answers") or [],
                checklist=dossier.get("checklist") or [],
                requirement_matrix=dossier.get("requirement_matrix") or [],
                evidence_catalog=(
                    dossier.get("evidence_catalog")
                    if dossier.get("schema_version") == "2.0"
                    else None
                ),
                resume_artifacts=self._verified_resume_artifacts(version),
            )
        except (DossierSizeError, TypeError, ValueError) as exc:
            raise ApplicationValidationError(str(exc)) from exc
        if (
            dossier.get("manifest_sha256") != bundle.manifest_sha256
            or dossier.get("manifest") != bundle.manifest
        ):
            raise ApplicationValidationError("Dossier manifest integrity check failed")
        return bundle

    def publish_dossier(
        self, user_id: int, application_id: str, data: ApplicationDossierCreate
    ) -> ApplicationResponse:
        application = self._application(user_id, application_id)
        if application.revision != data.expected_revision:
            raise ApplicationConflictError(
                f"Expected revision {data.expected_revision}, current revision is {application.revision}"
            )
        readiness = ApplicationReadinessService(self.db).build(user_id, application)
        if readiness.blocker_count:
            raise ApplicationValidationError(
                "Resolve the application readiness blockers before publishing a dossier"
            )
        version = self._resume_version(user_id, application.resume_version_id)
        if version is None:
            raise ApplicationValidationError("Link a published resume before creating a dossier")
        if not bool((version.quality_report or {}).get("passed")):
            raise ApplicationValidationError("The linked resume did not pass its quality checks")
        selected_ids = {str(value) for value in (version.selected_fact_ids or [])}
        snapshot_facts = (version.snapshot or {}).get("facts") or []
        facts_by_id = {
            str(fact.get("id")): fact
            for fact in snapshot_facts
            if isinstance(fact, dict)
            and fact.get("verification_status") == "confirmed"
            and str(fact.get("id")) in selected_ids
        }
        requirement_matrix: list[dict] = []
        all_evidence_ids = [
            str(fact_id) for row in data.requirement_matrix for fact_id in row.evidence_fact_ids
        ]
        missing = [fact_id for fact_id in set(all_evidence_ids) if fact_id not in facts_by_id]
        if missing:
            raise ApplicationValidationError(
                "Every dossier evidence reference must be a confirmed fact in the linked resume"
            )
        for row in data.requirement_matrix:
            evidence_fact_ids = [str(fact_id) for fact_id in row.evidence_fact_ids]
            requirement_matrix.append(
                {
                    "requirement": row.requirement.strip(),
                    "evidence_fact_ids": evidence_fact_ids,
                }
            )
        try:
            evidence_catalog = {
                fact_id: {
                    "fact_id": fact_id,
                    "fact_type": facts_by_id[fact_id].get("fact_type"),
                    "verification_status": "confirmed",
                    "snapshot": facts_by_id[fact_id],
                    "sha256": hashlib.sha256(canonical_json(facts_by_id[fact_id])).hexdigest(),
                }
                for fact_id in sorted(set(all_evidence_ids))
            }
        except (TypeError, ValueError) as exc:
            raise ApplicationValidationError(
                "A selected evidence fact cannot be serialized safely"
            ) from exc
        now = datetime.now(timezone.utc)
        dossier_id = str(uuid.uuid4())
        version_number = len(self._dossier_summaries(application)) + 1
        snapshot = application.job_snapshot or {}
        dossier: dict[str, Any] = {
            "schema_version": "2.0",
            "version_number": version_number,
            "application_revision": data.expected_revision + 1,
            "resume_version_id": version.id,
            "created_at": now.isoformat(),
            "readiness_fingerprint": readiness.fingerprint,
            "role": {
                "title": str(snapshot.get("title") or "Untitled role"),
                "company": str(snapshot.get("company") or "Unknown company"),
                "location": snapshot.get("location"),
            },
            "readiness": {
                "score_kind": readiness.score_kind,
                "status": readiness.status,
                "completeness_score": readiness.completeness_score,
                "fingerprint": readiness.fingerprint,
            },
            "cover_letter": data.cover_letter,
            "answers": [answer.model_dump(mode="json") for answer in data.answers],
            "checklist": [item.model_dump(mode="json") for item in data.checklist],
            "requirement_matrix": requirement_matrix,
            "evidence_catalog": evidence_catalog,
        }
        artifacts = self._verified_resume_artifacts(version)
        try:
            initial_bundle = build_dossier_bundle(
                dossier_id=dossier_id,
                version_number=version_number,
                application_revision=data.expected_revision + 1,
                application_id=application.id,
                created_at=dossier["created_at"],
                role=dossier["role"],
                resume_version_id=version.id,
                readiness=dossier["readiness"],
                cover_letter=dossier["cover_letter"],
                answers=dossier["answers"],
                checklist=dossier["checklist"],
                requirement_matrix=dossier["requirement_matrix"],
                evidence_catalog=dossier["evidence_catalog"],
                resume_artifacts=artifacts,
            )
        except (DossierSizeError, TypeError, ValueError) as exc:
            raise ApplicationValidationError(str(exc)) from exc
        dossier["manifest"] = initial_bundle.manifest
        dossier["manifest_sha256"] = initial_bundle.manifest_sha256
        event_payload = {"schema_version": "2.0", "dossier": dossier}
        try:
            event_size = len(canonical_json(event_payload))
        except (TypeError, ValueError) as exc:
            raise ApplicationValidationError("Dossier event is not valid JSON") from exc
        if event_size > MAX_DOSSIER_EVENT_BYTES:
            raise ApplicationValidationError(
                f"Dossier event exceeds the {MAX_DOSSIER_EVENT_BYTES}-byte limit"
            )
        self._advance_revision(application, data.expected_revision, now)
        self.db.add(
            ApplicationEvent(
                id=dossier_id,
                application_id=application.id,
                event_type="dossier_published",
                stage=None,
                occurred_at=now,
                note=None,
                payload=event_payload,
                created_at=now,
            )
        )
        self.db.commit()
        self.db.expire_all()
        return self._response(self._application(user_id, application_id))

    def dossier_bundle(self, user_id: int, application_id: str, dossier_id: str) -> DossierBundle:
        application = self._application(user_id, application_id)
        event = next(
            (
                item
                for item in application.events
                if item.id == dossier_id and item.event_type == "dossier_published"
            ),
            None,
        )
        if event is None:
            raise ApplicationNotFoundError("Application dossier not found")
        dossier = (event.payload or {}).get("dossier")
        if not isinstance(dossier, dict):
            raise ApplicationValidationError("Application dossier is invalid")
        return self._bundle_from_dossier(user_id, application, dossier_id, dossier)

    def list(self, user_id: int, *, offset: int = 0, limit: int = 200) -> list[ApplicationSummary]:
        rows = (
            self.db.query(
                Application.id,
                Application.job_id,
                Application.resume_version_id,
                Application.revision,
                Application.current_stage,
                Application.job_title,
                Application.job_company,
                Application.job_location,
                Application.latest_event_at,
                Application.updated_at,
                Application.next_action_task_id,
                Application.next_action_title,
                Application.next_action_at,
                Application.next_action_priority,
            )
            .filter(Application.user_id == user_id)
            .order_by(Application.updated_at.desc(), Application.id.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        summaries: list[ApplicationSummary] = []
        for item in rows:
            next_action = None
            projection = (
                item.next_action_task_id,
                item.next_action_title,
                item.next_action_priority,
            )
            if any(value is not None for value in projection):
                if any(value is None for value in projection):
                    raise ApplicationValidationError("Next-action projection is incomplete")
                next_action = ApplicationNextAction(
                    id=item.next_action_task_id,
                    title=item.next_action_title,
                    due_at=aware_utc(item.next_action_at),
                    priority=cast(ApplicationTaskPriority, item.next_action_priority),
                )
            latest_event_at = aware_utc(item.latest_event_at)
            updated_at = aware_utc(item.updated_at)
            if latest_event_at is None or updated_at is None:
                raise ApplicationValidationError(
                    "Application board projections are missing required timestamps"
                )
            summaries.append(
                ApplicationSummary(
                    id=item.id,
                    job_id=item.job_id,
                    resume_version_id=item.resume_version_id,
                    revision=item.revision,
                    current_stage=item.current_stage,
                    title=item.job_title,
                    company=item.job_company,
                    location=item.job_location,
                    latest_event_at=latest_event_at,
                    updated_at=updated_at,
                    next_action=next_action,
                )
            )
        return summaries
