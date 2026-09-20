"""CLI script to build a deterministic campaign ZIP archive from a source directory."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.campaign_archive_builder import build_campaign_archive  # noqa: E402


def main() -> int:
    if len(sys.argv) != 3:
        sys.stderr.write("Campaign archive build failed.\n")
        return 2

    source = Path(sys.argv[1])
    output = Path(sys.argv[2])
    try:
        result = build_campaign_archive(source, output)
        report = asdict(result)
        out = json.dumps(report, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        sys.stdout.write(out + "\n")
        return 0
    except Exception:
        sys.stderr.write("Campaign archive build failed.\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
