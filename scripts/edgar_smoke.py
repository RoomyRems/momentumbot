from __future__ import annotations

import json
import os

from momentumbot.providers.sec_edgar import SecEdgarClient


def main() -> int:
    user_agent = os.getenv(
        "SEC_USER_AGENT",
        "MomentumBot/0.2 https://github.com/RoomyRems/momentumbot",
    )
    client = SecEdgarClient(user_agent=user_agent)
    parsed = client.parsed_companyfacts("320193")  # Apple; stable smoke fixture issuer.
    public = parsed.public_float
    outstanding = parsed.outstanding_shares
    result = {
        "source": "data.sec.gov public APIs",
        "authentication_required": False,
        "issuer_cik": "0000320193",
        "public_float_disclosure_count": len(public),
        "outstanding_share_disclosure_count": len(outstanding),
        "public_float_first_measure_date": public[0].measure_date.isoformat() if public else None,
        "public_float_last_measure_date": public[-1].measure_date.isoformat() if public else None,
        "public_float_latest_available_at": public[-1].available_at.isoformat() if public else None,
        "outstanding_last_measure_date": outstanding[-1].measure_date.isoformat() if outstanding else None,
        "outstanding_latest_available_at": outstanding[-1].available_at.isoformat() if outstanding else None,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if not public or not outstanding:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
