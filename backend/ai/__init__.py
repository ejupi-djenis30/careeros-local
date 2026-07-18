"""Measured, schema-constrained local AI for CareerOS Local."""

from backend.ai.contracts import ValidationCode
from backend.ai.task_specs import TASK_SPECS, TaskSpec

__all__ = ["TASK_SPECS", "TaskSpec", "ValidationCode"]
