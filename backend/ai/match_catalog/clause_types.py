"""Typed clause structure shared by evidence extraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

_ConnectorKind = Literal[
    "start",
    "list",
    "additive",
    "adversative",
    "alternative",
    "scoped_absence",
]


_MarkerDirection = Literal["none", "forward", "backward", "both", "local"]


@dataclass(slots=True)
class _ClauseSegment:
    text: str
    connector: _ConnectorKind
    connector_text: str = ""
    explicit_status: str | None = None
    inherited_status: str | None = None
    marker_direction: _MarkerDirection = "none"
    marker_start: int | None = None
    marker_end: int | None = None
    absence_scope: bool = False

    @property
    def status(self) -> str:
        if self.absence_scope:
            return "exclusion"
        return self.explicit_status or self.inherited_status or "present"
