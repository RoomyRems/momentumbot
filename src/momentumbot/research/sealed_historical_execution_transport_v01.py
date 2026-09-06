"""Exact one-pass historical time-series transport, enabled after complete requote."""
from __future__ import annotations

import time
from pathlib import Path
import pandas as pd

from momentumbot.research import sealed_historical_execution_quote_v01 as quote
from momentumbot.research.sealed_historical_execution_acquisition_v01 import MAX_BILLABLE_BYTES, MAX_COST_USD, QUOTE_REPORT_CONTENT_SHA
from decimal import Decimal


class ExactTimeseriesHTTP:
    def __init__(self, requests: list[dict], parent_quote: dict, preflight_result: dict,
                 *, session, key: str, temporary_root: Path, progress=None, pause=time.sleep):
        quote.validate_requests(requests)
        quote.validate_report(parent_quote,requests,parent_quote['provenance'])
        if parent_quote['content_sha256'] != QUOTE_REPORT_CONTENT_SHA:
            raise ValueError('exact parent quote is required for wire ceilings')
        result = preflight_result['metadata_result']
        quote.validate_report(result,requests,result['provenance'])
        if preflight_result['preflight_passed'] is not True or not result['metadata_quote_gate_passed']:
            raise ValueError('downloads require complete requote')
        if result['total_billable_size_bytes'] > MAX_BILLABLE_BYTES or Decimal(result['total_quoted_cost_usd']) > Decimal(MAX_COST_USD):
            raise ValueError('download ceilings exceeded')
        self.requests = requests
        self.quote_rows = parent_quote['quote_rows']
        self.session, self.key = session, key
        self.root, self.progress, self.pause = temporary_root, progress, pause
        self.attempts, self.blocked = [], 0

    def ledger(self):
        return quote.seal({'http_attempts':len(self.attempts),'blocked_attempts':self.blocked,
            'attempts':self.attempts,'automatic_retries':0,'redirects_followed':0,'unregistered_endpoint_calls':0})

    def save(self):
        if self.progress: self.progress(self.ledger())

    def reject(self):
        self.blocked += 1; self.save()
        raise quote.MetadataFailure('blocked_request')

    def stream(self,url,data,basic_auth,path):
        index = len(self.attempts)
        if index >= len(self.requests): self.reject()
        request = self.requests[index]
        expected_path = self.root / f'request-{index:03d}.dbn.zst'
        try:
            valid = (url == 'https://hist.databento.com/v0/timeseries.get_range' and basic_auth is True
                and Path(path) == expected_path and not expected_path.exists() and not expected_path.is_symlink()
                and set(data) == {'dataset','start','end','symbols','schema','stype_in','stype_out','encoding','compression'}
                and data['dataset'] == request['dataset'] and data['schema'] == request['schema']
                and data['symbols'] == request['symbols'][0] and data['stype_in'] == 'raw_symbol'
                and data['stype_out'] == 'instrument_id' and data['encoding'] == 'dbn' and data['compression'] == 'zstd'
                and pd.Timestamp(data['start']).tzinfo is not None and pd.Timestamp(data['end']).tzinfo is not None
                and pd.Timestamp(data['start']).value == request['start_ns'] and pd.Timestamp(data['end']).value == request['end_ns'])
        except (ValueError,TypeError,KeyError):
            valid = False
        if not valid: self.reject()
        maximum = self.quote_rows[index]['billable_size_bytes'] + 65536
        attempt = {'ordinal':index+1,'request_id':request['request_id'],'request_content_sha256':quote.canonical_fingerprint(request),
                   'method':'timeseries.get_range','status':'pending','http_status':None,'wire_bytes':0,'maximum_wire_bytes':maximum}
        self.attempts.append(attempt); self.save(); self.pause(0.35)
        try:
            with self.session.post(url,data=data,auth=(self.key,''),headers={'Accept':'application/octet-stream','User-Agent':'momentumbot-historical-execution-input-acquisition-v01'},
                                   allow_redirects=False,timeout=(30,60),stream=True) as response:
                attempt['http_status'] = response.status_code
                if response.status_code != 200: raise quote.MetadataFailure('http_error')
                with expected_path.open('xb') as output:
                    for chunk in response.iter_content(65536):
                        attempt['wire_bytes'] += len(chunk)
                        if attempt['wire_bytes'] > maximum: raise quote.MetadataFailure('response_too_large')
                        output.write(chunk)
            from databento import DBNStore
            store = DBNStore.from_file(expected_path)
            attempt['status'] = 'complete'
            return store
        except quote.MetadataFailure:
            attempt['status'] = 'failed'; raise
        except Exception:
            attempt['status'] = 'failed'
            raise quote.MetadataFailure('network_error') from None
        finally:
            self.save()


def sdk_timeseries(transport: ExactTimeseriesHTTP):
    from databento.historical.api.timeseries import TimeseriesHttpAPI

    class ExactAPI(TimeseriesHttpAPI):
        def _get(self,*args,**kwargs): transport.reject()
        def _post(self,*args,**kwargs): transport.reject()
        def _stream(self,url,data,basic_auth,path=None):
            return transport.stream(url,data,basic_auth,path)

    return ExactAPI(key=transport.key,gateway='https://hist.databento.com')
