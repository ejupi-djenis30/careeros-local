import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from backend.ai.audit import fingerprint_output
from backend.ai.contracts import CoachResult
from backend.ai.models import AIExecution
from backend.ai.orchestrator import (
    AIValidationError,
    LocalAIOrchestrator,
    OrchestrationRequest,
)
from backend.ai.retrieval import EvidenceDocument
from backend.ai.task_specs import TASK_SPECS
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
from backend.core.config import settings
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

    @staticmethod
    def _verified_assistant_payload(
        message: CoachMessage,
        execution: AIExecution | None,
        user_id: int,
    ) -> bool:
        """Verify a visible assistant message against its content-free execution receipt."""
        metadata = message.generation_metadata
        if not isinstance(metadata, dict) or metadata.get("provenance") != "local_model_validated":
            return False
        contract_version = TASK_SPECS["coach"].version
        execution_id = metadata.get("execution_id")
        output_fingerprint = metadata.get("output_fingerprint")
        if (
            execution is None
            or not isinstance(execution_id, str)
            or execution.id != execution_id
            or execution.user_id != user_id
            or execution.task != "coach"
            or execution.accepted is not True
            or execution.contract_version != contract_version
            or metadata.get("contract_version") != contract_version
            or execution.model_id != message.model_id
            or not isinstance(output_fingerprint, str)
            or execution.output_fingerprint != output_fingerprint
        ):
            return False
        try:
            reconstructed = CoachResult.model_validate(
                {
                    "answer": message.content,
                    "claims": metadata.get("claims"),
                    "fact_citations": message.cited_fact_ids,
                    "job_citations": message.cited_job_ids,
                    "confidence": metadata.get("confidence"),
                    "missing_evidence": metadata.get("missing_evidence"),
                }
            )
        except Exception:
            return False
        return fingerprint_output(reconstructed) == output_fingerprint

    def _visible_messages(
        self,
        user_id: int,
        messages: list[CoachMessage],
    ) -> list[CoachMessage]:
        execution_ids = {
            execution_id
            for message in messages
            if message.role == "assistant"
            and isinstance(message.generation_metadata, dict)
            and isinstance((execution_id := message.generation_metadata.get("execution_id")), str)
        }
        executions = (
            self.db.query(AIExecution).filter(AIExecution.id.in_(execution_ids)).all()
            if execution_ids
            else []
        )
        executions_by_id = {execution.id: execution for execution in executions}
        visible: list[CoachMessage] = []
        for message in messages:
            if message.role == "user":
                visible.append(message)
                continue
            metadata: dict[str, Any] = (
                message.generation_metadata if isinstance(message.generation_metadata, dict) else {}
            )
            execution_id = metadata.get("execution_id")
            execution = (
                executions_by_id.get(execution_id) if isinstance(execution_id, str) else None
            )
            if self._verified_assistant_payload(message, execution, user_id):
                visible.append(message)
        return visible

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
                        "location": job.scraped_job.location,
                        "workload": job.scraped_job.workload,
                        "description": job.scraped_job.description,
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
            allowed_fact_ids = [fact.id for fact in facts]
            allowed_job_ids = [job.id for job in jobs]
            grounded_prompt = (
                f"QUESTION:\n{data.message}\n\n"
                f"ALLOWED_FACT_IDS: {json.dumps(allowed_fact_ids)}\n"
                f"ALLOWED_JOB_IDS: {json.dumps(allowed_job_ids)}\n"
                "Use only these exact IDs. If ALLOWED_JOB_IDS is empty, every job_ids and "
                "job_citations array must be empty. Keep every claim narrowly supported by "
                "the cited evidence; report uncertainty in missing_evidence instead of guessing."
            )
            timeout_seconds = max(0.05, float(settings.LLM_CALL_TIMEOUT_COACH))
            orchestrated = await LocalAIOrchestrator(provider, self.db).execute(
                OrchestrationRequest(
                    task_id="coach",
                    user_prompt=grounded_prompt,
                    evidence=self._evidence(facts, jobs),
                    user_id=user_id,
                    attempt_timeout_seconds=timeout_seconds / 2,
                    total_timeout_seconds=timeout_seconds,
                    max_output_tokens=600,
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
        allowed_fact_id_set = {fact.id for fact in facts}
        allowed_job_id_set = {job.id for job in jobs}
        fact_citations = result.fact_citations
        job_citations = result.job_citations
        if not set(fact_citations) <= allowed_fact_id_set:
            raise CoachValidationError("Local model returned unsupported career-fact citations")
        if not set(job_citations) <= allowed_job_id_set:
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
                "claims": [claim.model_dump(mode="json") for claim in result.claims],
                "confidence": result.confidence,
                "missing_evidence": result.missing_evidence,
                "provenance": "local_model_validated",
                "contract_version": "1.0.0",
                "execution_id": orchestrated.execution_id,
                "output_fingerprint": orchestrated.output_fingerprint,
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
                message_count=len(self._visible_messages(user_id, item.messages)),
                updated_at=item.updated_at,
            )
            for item in conversations
        ]

    def get(self, user_id: int, conversation_id: str) -> CoachConversationResponse:
        profile = self._profile(user_id)
        conversation = self._conversation(profile.id, conversation_id)
        response = CoachConversationResponse.model_validate(conversation)
        return response.model_copy(
            update={
                "messages": [
                    CoachMessageResponse.model_validate(message)
                    for message in self._visible_messages(user_id, conversation.messages)
                ]
            }
        )

    def delete(self, user_id: int, conversation_id: str) -> None:
        profile = self._profile(user_id)
        conversation = self._conversation(profile.id, conversation_id)
        self.db.delete(conversation)
        self.db.commit()
