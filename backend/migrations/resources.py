"""Locate migration assets from source, an installed wheel, or a frozen sidecar."""

from __future__ import annotations

import sys
from importlib.resources import files
from pathlib import Path


def migration_resource_directory() -> Path:
    """Return the filesystem directory containing the packaged Alembic environment."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        candidate = Path(frozen_root) / "backend" / "migrations"
    else:
        resource = files("backend.migrations")
        if not isinstance(resource, Path):
            raise RuntimeError(
                "CareerOS migration resources require a standard filesystem installation"
            )
        candidate = resource
    resolved = candidate.resolve()
    required = (resolved / "alembic.ini", resolved / "env.py", resolved / "versions")
    if not all(path.exists() for path in required):
        raise RuntimeError("CareerOS migration resources are incomplete")
    return resolved
