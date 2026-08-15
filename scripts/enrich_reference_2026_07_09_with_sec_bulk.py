from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    discovery = repo / "research" / "reference" / "2026-07-09" / "discovery_candidates.csv"
    companyfacts = repo / "data" / "sec" / "companyfacts.zip"
    submissions = repo / "data" / "sec" / "submissions.zip"
    output = repo / "artifacts" / "sec-enrichment-2026-07-09"

    missing = [path for path in (discovery, companyfacts, submissions) if not path.is_file()]
    if missing:
        print("MomentumBot cannot run SEC enrichment because these files are missing:")
        for path in missing:
            print(f"  - {path}")
        return 2

    command = [
        sys.executable,
        str(repo / "scripts" / "enrich_discovery_with_sec_bulk.py"),
        "--discovery",
        str(discovery),
        "--companyfacts",
        str(companyfacts),
        "--submissions",
        str(submissions),
        "--output",
        str(output),
    ]
    print("Reading the local SEC bulk archives. Nothing will be uploaded to GitHub.")
    completed = subprocess.run(command, cwd=repo, check=False)
    if completed.returncode == 0:
        print(f"SEC enrichment complete: {output}")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
