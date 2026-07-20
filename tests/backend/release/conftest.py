from __future__ import annotations

import re
from pathlib import Path

import pytest
from pytest import TempPathFactory


@pytest.fixture
def tmp_path(tmp_path_factory: TempPathFactory, request: pytest.FixtureRequest) -> Path:
    """Avoid Windows pytest's unsupported convenience symlinks in this release suite."""
    name = re.sub(r"[^A-Za-z0-9_.-]", "-", request.node.name)[:80]
    path = tmp_path_factory.getbasetemp() / name
    path.mkdir()
    return path
