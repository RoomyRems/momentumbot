"""Hosted bounded candidate coarse-RVOL capture."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from momentumbot.research import candidate_rvol_coarse
from hosted_scanner_source_cli import main

if __name__ == '__main__':
    try:
        sys.exit(main(candidate_rvol_coarse))
    except Exception:
        print('Candidate coarse-RVOL capture failed; evidence retained; no retry.', file=sys.stderr)
        sys.exit(2)
