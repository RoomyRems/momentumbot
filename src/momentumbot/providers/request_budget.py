"""Optional shared provider-request budget for bounded acquisition workflows.

The budget is inactive unless both environment variables are set.  When active,
every actual HTTP attempt consumes one unit before network access.  The shared
JSON state records only counts by hostname; URLs, headers, credentials, symbols,
and response data are never persisted.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse


BUDGET_FILE_ENV = "MOMENTUMBOT_PROVIDER_REQUEST_BUDGET_FILE"
BUDGET_LIMIT_ENV = "MOMENTUMBOT_PROVIDER_REQUEST_BUDGET_LIMIT"


def consume_provider_request(url: str) -> None:
    """Consume one configured shared request-budget unit before network access."""

    raw_path = os.getenv(BUDGET_FILE_ENV)
    raw_limit = os.getenv(BUDGET_LIMIT_ENV)
    if raw_path is None and raw_limit is None:
        return
    if not raw_path or not raw_limit:
        raise RuntimeError("provider request budget requires both environment values")
    try:
        limit = int(raw_limit)
    except ValueError as exc:
        raise RuntimeError("provider request budget limit must be an integer") from exc
    if limit <= 0:
        raise RuntimeError("provider request budget limit must be positive")
    path = Path(raw_path)
    if not path.is_absolute():
        raise RuntimeError("provider request budget file must be an absolute path")
    host = str(urlparse(url).hostname or "").lower()
    if not host:
        raise RuntimeError("provider request budget requires a URL hostname")
    path.parent.mkdir(parents=True, exist_ok=True)

    # GitHub's acquisition workflow is sequential, but the advisory lock keeps
    # the accounting correct if a future implementation overlaps requests.
    import fcntl

    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.seek(0)
        raw = handle.read().strip()
        if raw:
            try:
                state = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise RuntimeError("provider request budget state is invalid") from exc
        else:
            state = {"schema_version": 1, "total_attempts": 0, "by_host": {}}
        if state.get("schema_version") != 1:
            raise RuntimeError("provider request budget schema is invalid")
        total = state.get("total_attempts")
        by_host = state.get("by_host")
        if not isinstance(total, int) or total < 0 or not isinstance(by_host, dict):
            raise RuntimeError("provider request budget state is invalid")
        if total >= limit:
            raise RuntimeError("provider request budget exhausted before network access")
        host_count = by_host.get(host, 0)
        if not isinstance(host_count, int) or host_count < 0:
            raise RuntimeError("provider request budget host count is invalid")
        by_host[host] = host_count + 1
        state = {
            "schema_version": 1,
            "total_attempts": total + 1,
            "by_host": dict(sorted(by_host.items())),
        }
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps(state, separators=(",", ":"), sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def load_provider_request_budget(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != 1
        or not isinstance(payload.get("total_attempts"), int)
        or not isinstance(payload.get("by_host"), dict)
    ):
        raise ValueError("provider request budget state is invalid")
    return payload
