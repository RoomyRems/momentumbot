from __future__ import annotations

import gzip
import json
import time
import urllib.error
import urllib.request
from typing import Any

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _decode_body(raw: bytes, encoding: str) -> bytes:
    return gzip.decompress(raw) if "gzip" in encoding.lower() else raw


def get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout_seconds: int = 30,
    max_retries: int = 5,
) -> Any:
    """GET JSON with bounded retries for throttling/transient provider failures.

    The exception deliberately omits the URL because some providers authenticate
    with a query parameter. This keeps API keys out of logs even on failure.
    """
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                raw = _decode_body(
                    response.read(), response.headers.get("Content-Encoding") or ""
                )
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = _decode_body(
                exc.read(), exc.headers.get("Content-Encoding") or ""
            )
            text = body.decode("utf-8", errors="replace")[:500]
            if exc.code not in _RETRYABLE_STATUS or attempt >= max_retries:
                raise RuntimeError(
                    f"HTTP {exc.code} for provider request: {text}"
                ) from exc
            retry_after = exc.headers.get("Retry-After")
            try:
                delay = float(retry_after) if retry_after else min(2**attempt, 8)
            except ValueError:
                delay = min(2**attempt, 8)
            time.sleep(max(0.25, min(delay, 15.0)))
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt >= max_retries:
                raise RuntimeError(f"provider network failure: {type(exc).__name__}") from exc
            time.sleep(min(2**attempt, 8))
    raise AssertionError("unreachable")
