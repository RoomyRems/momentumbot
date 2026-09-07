"""Three-call transport for one preregistered diagnostic, with no retry route."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from momentumbot.research import sealed_historical_execution_diagnostic_v01 as diag
from momentumbot.research import sealed_historical_execution_quote_v01 as quote
from momentumbot.research.sealed_historical_metadata_transport_v01 import _JSONResponse, sdk_metadata
from momentumbot.research.sealed_historical_execution_transport_v01 import sdk_timeseries


class DiagnosticHTTP:
    def __init__(self, *, session, key: str, temporary_root: Path, progress=None):
        self.session, self.key, self.root, self.progress = session, key, temporary_root, progress
        self.attempts, self.calls, self.blocked = [], [], 0

    def ledger(self) -> dict:
        return diag.seal({'contract_id':diag.CONTRACT_ID,'attempts':self.attempts,'metadata_calls':self.calls,
            'http_attempts':len(self.attempts),'blocked_attempts':self.blocked,
            'automatic_retries':0,'redirects_followed':0,'unregistered_endpoint_calls':0})

    def save(self):
        if self.progress:
            self.progress(self.ledger())

    def reject(self):
        self.blocked += 1
        self.save()
        raise quote.MetadataFailure('blocked_request')

    def valid_data(self, data, *, stream: bool) -> bool:
        r = diag.request()
        fields = {'dataset','schema','symbols','start','end','stype_in','stype_out'}
        if stream:
            fields |= {'encoding','compression'}
        try:
            return (set(data)==fields and data['dataset']==r['dataset'] and data['schema']==r['schema']
                and data['symbols']==r['symbols'][0] and data['stype_in']=='raw_symbol'
                and data['stype_out']=='instrument_id' and pd.Timestamp(data['start']).tzinfo is not None
                and pd.Timestamp(data['end']).tzinfo is not None
                and pd.Timestamp(data['start']).value==r['start_ns'] and pd.Timestamp(data['end']).value==r['end_ns']
                and (not stream or (data['encoding']=='dbn' and data['compression']=='zstd')))
        except (ValueError,TypeError,KeyError):
            return False

    def post(self, url, data=None, params=None, basic_auth=False):
        index = len(self.attempts)
        if (index >= 2 or self.blocked or params is not None or basic_auth is not True
            or not self.valid_data(data,stream=False)):
            self.reject()
        method = quote.METHODS[index]
        if url != 'https://hist.databento.com/v0/metadata.'+method:
            self.reject()
        if any(c['status']!='success' for c in self.calls):
            self.reject()
        call = {'ordinal':index+1,'method':method,'request_content_sha256':diag.REQUEST_SHA,
                'status':'pending','value':None,'error':None}
        attempt = {'ordinal':index+1,'method':'metadata.'+method,'request_content_sha256':diag.REQUEST_SHA,
                   'status':'pending','http_status':None,'wire_bytes':0,'maximum_wire_bytes':65536}
        self.calls.append(call); self.attempts.append(attempt); self.save()
        try:
            with self.session.post(url,data=data,auth=(self.key,''),
                headers={'Accept':'application/json','User-Agent':'momentumbot-execution-diagnostic-v01'},
                allow_redirects=False,timeout=(30,30),stream=True) as response:
                attempt['http_status'] = response.status_code
                if response.status_code != 200:
                    raise quote.MetadataFailure('http_error')
                body = bytearray()
                for chunk in response.iter_content(8192):
                    attempt['wire_bytes'] += len(chunk)
                    if attempt['wire_bytes'] > 65536:
                        raise quote.MetadataFailure('response_too_large')
                    body.extend(chunk)
                value = json.loads(body)
            call['value'] = quote._value(method,value)
            call['status'] = attempt['status'] = 'success'
            return _JSONResponse(value)
        except quote.MetadataFailure as exc:
            call.update(status='failed',error=exc.code); attempt['status']='failed'
            raise
        except Exception:
            call.update(status='failed',error='invalid_result'); attempt['status']='failed'
            raise quote.MetadataFailure('invalid_result') from None
        finally:
            self.save()

    def requote(self) -> dict:
        api = sdk_metadata(self)
        for method in quote.METHODS:
            try:
                getattr(api,method)(**quote.request_kwargs(diag.request()))
            except Exception:
                break
        return diag.preflight(self.calls,len(self.attempts),self.blocked)

    def stream(self, url, data, basic_auth, path):
        expected = self.root / 'diagnostic.dbn.zst'
        if (len(self.attempts)!=2 or self.blocked or basic_auth is not True
            or url!='https://hist.databento.com/v0/timeseries.get_range'
            or not self.valid_data(data,stream=True) or path is None or Path(path)!=expected
            or expected.exists() or expected.is_symlink()
            or not diag.preflight(self.calls,len(self.attempts),self.blocked)['preflight_passed']):
            self.reject()
        attempt = {'ordinal':3,'method':'timeseries.get_range','request_content_sha256':diag.REQUEST_SHA,
                   'status':'pending','http_status':None,'wire_bytes':0,'maximum_wire_bytes':diag.MAX_WIRE_BYTES,
                   'dbn_file_sha256':None}
        self.attempts.append(attempt); self.save()
        try:
            with self.session.post(url,data=data,auth=(self.key,''),
                headers={'Accept':'application/octet-stream','User-Agent':'momentumbot-execution-diagnostic-v01'},
                allow_redirects=False,timeout=(30,60),stream=True) as response:
                attempt['http_status'] = response.status_code
                if response.status_code != 200:
                    raise quote.MetadataFailure('http_error')
                with expected.open('xb') as output:
                    for chunk in response.iter_content(65536):
                        attempt['wire_bytes'] += len(chunk)
                        if attempt['wire_bytes'] > diag.MAX_WIRE_BYTES:
                            raise quote.MetadataFailure('response_too_large')
                        output.write(chunk)
            attempt['dbn_file_sha256'] = diag.file_sha(expected)
            from databento import DBNStore
            store = DBNStore.from_file(expected)
            attempt['status'] = 'complete'
            return store
        except quote.MetadataFailure:
            attempt['status'] = 'failed'
            raise
        except Exception:
            attempt['status'] = 'failed'
            raise quote.MetadataFailure('network_error') from None
        finally:
            self.save()

    def download(self):
        return sdk_timeseries(self).get_range(path=str(self.root/'diagnostic.dbn.zst'),
                                              **quote.request_kwargs(diag.request()))
