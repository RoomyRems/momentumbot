from __future__ import annotations

import gzip
import json
import urllib.error
import urllib.request
from typing import Any


def get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout_seconds: int = 30,
) -> Any:
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read()
            encoding = (response.headers.get("Content-Encoding") or "").lower()
            if "gzip" in encoding:
                raw = gzip.decompress(raw)
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read()
        if "gzip" in (exc.headers.get("Content-Encoding") or "").lower():
            body = gzip.decompress(body)
        text = body.decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"HTTP {exc.code} for provider request: {text}") from exc
