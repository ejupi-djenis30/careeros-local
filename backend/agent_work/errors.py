"""Stable content-free domain errors for agent work."""


class AgentWorkError(RuntimeError):
    """An operation failed without exposing source values."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
