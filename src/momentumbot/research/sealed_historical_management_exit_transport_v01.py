"""Versioned exact-exit adapters over the immutable bounded HTTP mechanics."""
from copy import deepcopy
import time

from momentumbot.research import sealed_historical_management_exit_acquisition_v01 as acq
from momentumbot.research import sealed_historical_management_exit_quote_v01 as quote
from momentumbot.research.sealed_historical_metadata_transport_v01 import MetadataOnlyHTTP as ParentMetadata, sdk_metadata
from momentumbot.research.sealed_historical_execution_transport_v01 import ExactTimeseriesHTTP as ParentTimeseries, sdk_timeseries


class MetadataOnlyHTTP(ParentMetadata):
    def __init__(self, requests, *, session, key, progress=None, pause=time.sleep):
        acq.validate_requests(requests)
        self.expected = [(deepcopy(row), method) for row in requests for method in quote.METHODS]
        self.session, self.key, self.progress, self.pause = session, key, progress, pause
        self.attempts, self.blocked = [], 0


class ExactTimeseriesHTTP(ParentTimeseries):
    def __init__(self, requests, parent_quote, preflight_result, *, session, key, temporary_root,
                 progress=None, pause=time.sleep):
        acq.validate_requests(requests)
        quote.require_exact(preflight_result, acq.preflight(requests, parent_quote, preflight_result['calls'],
            preflight_result['http_attempts'], preflight_result['blocked_attempts']), 'exact exit preflight')
        if preflight_result['preflight_passed'] is not True:
            raise ValueError('complete bounded exit requote required')
        self.requests = deepcopy(requests)
        self.quote_rows = deepcopy(parent_quote['quote_rows'])
        self.session, self.key = session, key
        self.root, self.progress, self.pause = temporary_root, progress, pause
        self.attempts, self.blocked = [], 0
