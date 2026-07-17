import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.ai.contracts import CoachResult
from backend.ai.orchestrator import (
    AIValidationError,
    LocalAIOrchestrator,
    OrchestrationRequest,
)
from backend.ai.retrieval import EvidenceDocument
from backend.career.coach_models import CoachConversation, CoachMessage
from backend.career.coach_schemas import (
    CoachConversationResponse,
    CoachConversationSummary,
    CoachMessageCreate,
    CoachMessageResponse,
    CoachReply,
)
from backend.career.models import CandidateProfile, CareerFact
from backend.career.repository import CareerProfileRepository
from backend.inference.ports import LocalInferenceFactory
from backend.models import Job


class CoachNotFoundError(LookupError):
    pass


class CoachValidationError(ValueError):
    pass


class CoachUnavailableError(RuntimeError):
    pass


class CareerCoachService:
    def __init__(self, db: Session, *, inference_factory: LocalInferenceFactory):
        self.db = db
        self.inference_factory = inference_factory

    def _profile(self, user_id: int) -> CandidateProfile:
        profile = CareerProfileRepository(self.db).get_by_user(user_id)
        if profile is None:
            raise CoachValidationError("Create the career profile before using the coach")
        return profile

    def _conversation(self, profile_id: str, conversation_id: str) -> CoachConversation:
        conversation = (
            self.db.query(CoachConversation)
            .filter(
                CoachConversation.id == conversation_id,
                CoachConversation.profile_id == profile_id,
            )
            .first()
        )
        if conversation is None:
            raise CoachNotFoundError("Conversation not found")
        return conversation

    def _select_facts(
        self, profile: CandidateProfile, question: str, requested_ids: list[str]
    ) -> list[CareerFact]:
        active = [
            fact
            for fact in profile.facts
            if fact.archived_at is None
            and fact.verification_status == "confirmed"
            and fact.fact_type != "reference"
        ]
        by_id = {fact.id: fact for fact in active}
        if requested_ids:
            missing = [fact_id for fact_id in requested_ids if fact_id not in by_id]
            if missing:
                raise CoachValidationError("Career facts not found: " + ", ".join(missing))
            return [by_id[fact_id] for fact_id in requested_ids]
        # The shared BM25 retriever performs final deterministic ranking within the
        # task-specific context budget. Stable position ordering avoids hidden heuristics.
        return sorted(active, key=lambda fact: (fact.position, fact.id))[:30]

    def _select_jobs(self, user_id: int, requested_ids: list[int]) -> list[Job]:
        if not requested_ids:
            return []
        jobs = self.db.query(Job).filter(Job.user_id == user_id, Job.id.in_(requested_ids)).all()
        by_id = {job.id: job for job in jobs}
        missing = [job_id for job_id in requested_ids if job_id not in by_id]
        if missing:
            raise CoachValidationError(
                "Jobs not found: " + ", ".join(str(item) for item in missing)
            )
        return [by_id[job_id] for job_id in requested_ids]

    @staticmethod
    def _evidence(facts: list[CareerFact], jobs: list[Job]) -> tuple[EvidenceDocument, ...]:
        documents = [
            EvidenceDocument(
                id=fact.id,
                kind="fact",
                text=json.dumps(
                    {"fact_type": fact.fact_type, "payload": fact.payload},
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                ),
                metadata={"verification_status": fact.verification_status},
            )
            for fact in facts
        ]
        documents.extend(
            EvidenceDocument(
                id=str(job.id),
                kind="job",
                text=json.dumps(
                    {
                        "title": job.scraped_job.title,
                        "company": job.scraped_job.company,
                        "normalized": job.scraped_job.normalized_job_data,
                        "match_score": job.affinity_score,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                ),
            )
            for job in jobs
        )
        return tuple(documents)

    async def reply(self, user_id: int, data: CoachMessageCreate) -> CoachReply:
        profile = self._profile(user_id)
        facts = self._select_facts(profile, data.message, data.fact_ids)
        jobs = self._select_jobs(user_id, data.job_ids)
        if data.conversation_id:
            conversation = self._conversation(profile.id, data.conversation_id)
        else:
            conversation = CoachConversation(
                profile_id=profile.id,
                title=data.message[:157] + ("…" if len(data.message) > 157 else ""),
            )

        try:
            provider = self.inference_factory("default")
            orchestrated = await LocalAIOrchestrator(provider, self.db).execute(
                OrchestrationRequest(
                    task_id="coach",
                    user_prompt=data.message,
                    evidence=self._evidence(facts, jobs),
                    user_id=user_id,
                )
            )
            result = orchestrated.output
            if not isinstance(result, CoachResult):
                raise TypeError("coach task returned an unexpected contract")
        except AIValidationError as exc:
            raise CoachValidationError(
                "The local model answer could not be grounded in the selected evidence"
            ) from exc
        except Exception as exc:
            raise CoachUnavailableError("The configured local model is unavailable") from exc
        allowed_fact_ids = {fact.id for fact in facts}
        allowed_job_ids = {job.id for job in jobs}
        fact_citations = result.fact_citations
        job_citations = result.job_citations
        if not set(fact_citations) <= allowed_fact_ids:
            raise CoachValidationError("Local model returned unsupported career-fact citations")
        if not set(job_citations) <= allowed_job_ids:
            raise CoachValidationError("Local model returned unsupported job citations")
        if (facts or jobs) and not fact_citations and not job_citations:
            raise CoachValidationError("Local model answer is not grounded in local evidence")

        now = datetime.now(timezone.utc)
        if not data.conversation_id:
            self.db.add(conversation)
            self.db.flush()
        conversation.updated_at = now
        self.db.add(
            CoachMessage(
                conversation_id=conversation.id,
                role="user",
                content=data.message,
                cited_fact_ids=[],
                cited_job_ids=[],
                model_id=None,
                generation_metadata={},
                created_at=now,
            )
        )
        assistant = CoachMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=result.answer.strip()[:30_000],
            cited_fact_ids=fact_citations,
            cited_job_ids=job_citations,
            model_id=provider.model_id,
            generation_metadata={
                "mode": "local",
                "career_fact_count": len(facts),
                "job_count": len(jobs),
                "claim_count": len(result.claims),
                "confidence": result.confidence,
                "missing_evidence": result.missing_evidence,
                "repair_count": orchestrated.repair_count,
                "usage": orchestrated.usage,
            },
            created_at=now,
        )
        self.db.add(assistant)
        conversation.updated_at = assistant.created_at
        self.db.commit()
        self.db.refresh(assistant)
        return CoachReply(
            conversation_id=conversation.id,
            message=CoachMessageResponse.model_validate(assistant),
        )

    def list(self, user_id: int) -> list[CoachConversationSummary]:
        profile = self._profile(user_id)
        conversations = (
            self.db.query(CoachConversation)
            .filter(CoachConversation.profile_id == profile.id)
            .order_by(CoachConversation.updated_at.desc())
            .all()
        )
        return [
            CoachConversationSummary(
                id=item.id,
                title=item.title,
                message_count=len(item.messages),
                updated_at=item.updated_at,
            )
            for item in conversations
        ]

    def get(self, user_id: int, conversation_id: str) -> CoachConversationResponse:
        profile = self._profile(user_id)
        return CoachConversationResponse.model_validate(
            self._conversation(profile.id, conversation_id)
        )

    def delete(self, user_id: int, conversation_id: str) -> None:
        profile = self._profile(user_id)
        conversation = self._conversation(profile.id, conversation_id)
        self.db.delete(conversation)
        self.db.commit()
