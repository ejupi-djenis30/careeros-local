"""Locate migration assets from source, an installed wheel, or a frozen sidecar."""

from __future__ import annotations

import sys
from importlib.resources import files
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


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
    required_files = (resolved / "alembic.ini", resolved / "env.py", resolved / "script.py.mako")
    versions = resolved / "versions"
    if not all(path.is_file() for path in required_files) or not versions.is_dir():
        raise RuntimeError("CareerOS migration resources are incomplete")
    return resolved


def current_migration_head(migration_root: Path | None = None) -> str:
    """Validate that packaged migrations have one base and one converged head."""

    root = (migration_root or migration_resource_directory()).resolve()
    configuration = Config(str(root / "alembic.ini"))
    configuration.set_main_option("script_location", str(root))
    scripts = ScriptDirectory.from_config(configuration)
    bases = scripts.get_bases()
    heads = scripts.get_heads()
    if len(bases) != 1 or len(heads) != 1:
        raise RuntimeError("CareerOS migration history must have exactly one base and one head")
    # Loading the complete walk detects missing parents, duplicate revision IDs
    # and cycles before a user's vault is opened.
    revisions = list(scripts.walk_revisions(base="base", head="heads"))
    if not revisions or revisions[0].revision != heads[0] or revisions[-1].revision != bases[0]:
        raise RuntimeError("CareerOS migration history is disconnected")
    return heads[0]
