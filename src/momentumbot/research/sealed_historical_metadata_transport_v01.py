"""Restrict the pinned SDK to the 180 exact metadata POSTs, with no retries."""
from __future__ import annotations

import json
import time

import pandas as pd

from momentumbot.research.sealed_historical_execution_quote_v01 import (
    METHODS, MetadataFailure, seal, validate_requests,
)


class _JSONResponse:
    def __init__(self, value):
        self.value = value

    def json(self):
        return self.value


class MetadataOnlyHTTP:
    def __init__(self, requests: list[dict], *, session, key: str, progress=None, pause=time.sleep):
        validate_requests(requests)
        self.expected = [(json.loads(json.dumps(row)), method) for row in requests for method in METHODS]
        self.session = session
        self.key = key
        self.progress = progress
        self.pause = pause
        self.attempts = []
        self.blocked = 0

    def ledger(self) -> dict:
        return seal({"http_attempts": len(self.attempts), "blocked_attempts": self.blocked,
                     "attempts": self.attempts, "automatic_retries": 0,
                     "redirects_followed": 0, "non_metadata_calls": 0})

    def save(self):
        if self.progress:
            self.progress(self.ledger())

    def reject(self):
        self.blocked += 1
        self.save()
        raise MetadataFailure("blocked_request")

    def post(self, url, data=None, params=None, basic_auth=False):
        if len(self.attempts) >= len(self.expected):
            self.reject()
        row, method = self.expected[len(self.attempts)]
        expected_url = f"https://hist.databento.com/v0/metadata.{method}"
        try:
            valid = (
                url == expected_url and params is None and basic_auth is True
                and set(data) == {"dataset", "start", "end", "symbols", "schema", "stype_in", "stype_out"}
                and data["dataset"] == row["dataset"] and data["symbols"] == row["symbols"][0]
                and data["schema"] == row["schema"] and data["stype_in"] == "raw_symbol"
                and data["stype_out"] == "instrument_id"
                and pd.Timestamp(data["start"]).tzinfo is not None
                and pd.Timestamp(data["end"]).tzinfo is not None
                and pd.Timestamp(data["start"]).value == row["start_ns"]
                and pd.Timestamp(data["end"]).value == row["end_ns"]
            )
        except (TypeError, ValueError, KeyError):
            valid = False
        if not valid:
            self.reject()
        attempt = {"ordinal": len(self.attempts) + 1, "request_id": row["request_id"],
                   "method": method, "status": "pending", "http_status": None}
        self.attempts.append(attempt)
        self.save()
        self.pause(0.35)
        try:
            with self.session.post(url, data=data, auth=(self.key, ""),
                                   headers={"Accept": "application/json", "User-Agent": "momentumbot-historical-metadata-quote-v01"},
                                   allow_redirects=False, timeout=(30, 30), stream=True) as response:
                attempt["http_status"] = response.status_code
                if response.status_code != 200:
                    raise MetadataFailure("http_error")
                body = bytearray()
                for chunk in response.iter_content(8192):
                    body.extend(chunk)
                    if len(body) > 65536:
                        raise MetadataFailure("response_too_large")
                value = json.loads(body)
            attempt["status"] = "success"
            return _JSONResponse(value)
        except MetadataFailure:
            attempt["status"] = "error"
            raise
        except Exception:
            attempt["status"] = "error"
            raise MetadataFailure("network_error") from None
        finally:
            self.save()


def sdk_metadata(transport: MetadataOnlyHTTP):
    from databento.historical.api.metadata import MetadataHttpAPI

    class ExactMetadataAPI(MetadataHttpAPI):
        def _get(self, *args, **kwargs):
            transport.reject()

        def _post(self, url, data=None, params=None, basic_auth=False):
            return transport.post(url, data, params, basic_auth)

    return ExactMetadataAPI(key=transport.key, gateway="https://hist.databento.com")
