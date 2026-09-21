"""CLI script to validate a campaign archive and output an aggregate-only report."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.campaigns.aggregate_validation import build_campaign_validation_report  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        sys.stderr.write("Campaign archive validation failed.\n")
        return 2

    target = Path(sys.argv[1])
    try:
        if not target.is_file():
            sys.stderr.write("Campaign archive validation failed.\n")
            return 2
        data = target.read_bytes()
        report = build_campaign_validation_report(data)
        out = json.dumps(report, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        sys.stdout.write(out + "\n")
        return 0
    except Exception:
        sys.stderr.write("Campaign archive validation failed.\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
