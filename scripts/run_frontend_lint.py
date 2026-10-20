"""Run the frontend lint hook with explicitly installed local dependencies."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"


def main() -> int:
    eslint = FRONTEND / "node_modules" / ".bin" / ("eslint.cmd" if os.name == "nt" else "eslint")
    if not eslint.is_file():
        raise RuntimeError(
            "Frontend dependencies are missing. Run npm ci --ignore-scripts --prefix frontend "
            "with the Node version in .nvmrc before running the lint hook."
        )
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if npm is None:
        raise RuntimeError(
            "npm is unavailable. Install the Node version in .nvmrc and activate it."
        )
    subprocess.run([npm, "run", "lint"], cwd=FRONTEND, check=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        raise SystemExit(str(error)) from None
