#!/usr/bin/env sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON="$PROJECT_ROOT/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  echo "Create the locked .venv before packaging CareerOS Local." >&2
  exit 1
fi

exec "$PYTHON" "$PROJECT_ROOT/scripts/run_desktop.py" build "$@"
