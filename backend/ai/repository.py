from __future__ import annotations

from sqlalchemy.orm import Session

from backend.ai.models import AIEvaluationRun, AIExecution


class AIRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add_execution(self, execution: AIExecution) -> AIExecution:
        self.db.add(execution)
        self.db.commit()
        self.db.refresh(execution)
        return execution

    def add_evaluation(self, evaluation: AIEvaluationRun) -> AIEvaluationRun:
        self.db.add(evaluation)
        self.db.commit()
        self.db.refresh(evaluation)
        return evaluation

    def list_evaluations(self, *, limit: int = 50) -> list[AIEvaluationRun]:
        bounded = max(1, min(int(limit), 200))
        return (
            self.db.query(AIEvaluationRun)
            .order_by(AIEvaluationRun.created_at.desc())
            .limit(bounded)
            .all()
        )
