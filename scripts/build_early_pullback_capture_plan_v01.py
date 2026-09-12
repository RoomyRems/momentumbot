"""Offline-only fixed-panel calendar and capture-plan registration."""
import argparse
import json
from pathlib import Path
import sys

from run_offline_python_v13 import deny_external_io


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true", help="write new registration/plan once")
    args = parser.parse_args()
    sys.addaudithook(deny_external_io)
    from momentumbot.research import early_pullback_capture_plan_v01 as m
    root = Path(__file__).resolve().parents[1]
    if args.freeze:
        outputs = [(root / m.CONTRACT_PATH, m.registration(root)),
                   (root / m.PLAN_PATH, m.capture_plan(m.parent.frozen(root / m.CALENDAR_PATH)))]
        m.require(all(not p.exists() for p, _ in outputs), "frozen output already exists")
        for path, value in outputs:
            m.parent.write_once(path, value)
    contract = m.validate_registration(root)
    print(json.dumps({"status": "verified_unarmed_plan", "registration_sha256": contract["content_sha256"],
        "scheduled_full_sessions": len(m.DATES), "census_initial_requests": len(m.DATES) + 1,
        "census_http_ceiling_if_separately_armed": m.MAX_CENSUS_ATTEMPTS, **m.BOUNDARY}, sort_keys=True))


if __name__ == "__main__":
    main()
