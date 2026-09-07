"""Narrowly bind the unchanged metadata transport to the 80 exit requests."""
from __future__ import annotations

import json
import time

from momentumbot.research.sealed_historical_management_exit_quote_v01 import METHODS, validate_requests
from momentumbot.research.sealed_historical_metadata_transport_v01 import MetadataOnlyHTTP as ParentHTTP, sdk_metadata


class MetadataOnlyHTTP(ParentHTTP):
    """Only request registration changes; POST checks and SDK routing are inherited."""

    def __init__(self, requests: list[dict], *, session, key: str, progress=None, pause=time.sleep):
        validate_requests(requests)
        self.expected = [(json.loads(json.dumps(row)), method) for row in requests for method in METHODS]
        self.session = session
        self.key = key
        self.progress = progress
        self.pause = pause
        self.attempts = []
        self.blocked = 0
