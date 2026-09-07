"""Exact-window diagnostic regression with synthetic HTTP and real pinned DBN decoding."""
from __future__ import annotations

from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
from datetime import date, timedelta
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace as N
import unittest
from unittest.mock import patch
import zipfile

import yaml
from momentumbot.research import sealed_historical_execution_empty_diagnostic_v01 as d
from momentumbot.research import sealed_historical_execution_quote_v01 as q
from momentumbot.research.sealed_historical_execution_empty_diagnostic_transport_v01 import DiagnosticHTTP

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import diagnose_sealed_historical_execution_empty_input_v01 as runner
HAS_SDK = importlib.util.find_spec('databento') is not None


def body(*, empty=True, symbol='JVA', mappings=True, start_delta=0, truncate=False, compressed=True, duplicate=False):
    import databento_dbn as dbn
    import zstandard
    r = d.request(); day = date.fromisoformat(r['trading_date'])
    meta = dbn.Metadata(dataset='XNAS.ITCH',start=r['start_ns']+start_delta,end=r['end_ns'],
        stype_in=dbn.SType.RAW_SYMBOL,stype_out=dbn.SType.INSTRUMENT_ID,schema=dbn.Schema.MBP_1,
        symbols=[symbol],mappings=[N(raw_symbol=symbol,intervals=[
            N(start_date=day,end_date=day+timedelta(days=1),symbol='1')])] if mappings else [])
    raw = meta.encode()
    if not empty:
        ns = r['start_ns']+1
        message = dbn.MBP1Msg(publisher_id=2,instrument_id=1,ts_event=ns-1,
            price=1_000_000_000,size=10,action=dbn.Action.ADD,side=dbn.Side.BID,depth=0,
            ts_recv=ns,sequence=1,levels=dbn.BidAskPair(bid_px=1_000_000_000,
                ask_px=1_010_000_000,bid_sz=10,ask_sz=20))
        raw += bytes(message)*(2 if duplicate else 1)
    if truncate: raw=raw[:-1]
    return zstandard.ZstdCompressor().compress(raw) if compressed else raw


class Response:
    def __init__(self, body, status=200): self.body,self.status_code=body,status
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def iter_content(self,size):
        for i in range(0,len(self.body),size): yield self.body[i:i+size]


class Session:
    def __init__(self, raw=None, *, size=d.MAX_BILLABLE_BYTES, cost=d.MAX_COST_USD, status=200):
        self.replies = [json.dumps(size).encode(),json.dumps(cost).encode(),raw]
        self.status,self.calls,self.closed=status,[],False
    def post(self,url,**kwargs):
        i=len(self.calls);self.calls.append((url,kwargs))
        return Response(self.replies[i],self.status)
    def close(self): self.closed=True


def calls():
    return [{'ordinal':i+1,'method':method,'request_content_sha256':d.REQUEST_SHA,
        'status':'success','value':value,'error':None}
        for i,(method,value) in enumerate(zip(q.METHODS,(d.MAX_BILLABLE_BYTES,d.MAX_COST_USD),strict=True))]


def rebuild_inventory(output):
    inv=d.frozen(output/'diagnostic-inventory.json')
    for name in inv['files']:
        path=output/name;inv['files'][name]={'sha256':d.file_sha(path),'bytes':path.stat().st_size}
    d.write_json(output/'diagnostic-inventory.json',d.seal({k:v for k,v in inv.items() if k!='content_sha256'}),replace=True)


class Harness:
    def __init__(self, base, raw):
        self.base,self.output,self.pre=base,base/'output',base/'pre'
        self.pre.mkdir()
        self.path=base/'synthetic-execution.json'
        self.execution=d.execution_payload(code_commit='a'*40,code_tree='b'*40,
            workflow_sha256=d.file_sha(ROOT/d.WORKFLOW_PATH),ci_run_id='123',validation_run_id='124')
        d.write_json(self.path,self.execution)
        self.env={'EXECUTION_CODE_COMMIT_SHA':'a'*40,'EXECUTION_CODE_TREE_SHA':'b'*40,
            'GITHUB_SHA':'c'*40,'GITHUB_RUN_ID':'125','GITHUB_RUN_ATTEMPT':'1',
            'GITHUB_REPOSITORY':'RoomyRems/momentumbot','GITHUB_EVENT_NAME':'push',
            'GITHUB_REF':'refs/heads/phase-3-historical-snapshot','DATABENTO_API_KEY':'synthetic-test-key'}
        pins=dict(re.findall(r'^([A-Za-z0-9_.-]+)==([^\s\\]+)',(ROOT/q.LOCK_PATH).read_text(),re.M))
        self.environment=d.seal({'implementation':'CPython','python_version':'3.12.14',
            'requirements_sha256':q.LOCK_SHA256,'package_versions':pins})
        (self.pre/'consumption-ref.json').write_text(json.dumps({'ref':d.CONSUMPTION_REF,'object':{'sha':'c'*40}}))
        self.session=Session(raw)
    def context(self):
        stack=ExitStack()
        stack.enter_context(patch.dict(os.environ,self.env,clear=True))
        stack.enter_context(patch.object(d,'EXECUTION_PATH',str(self.path)))
        stack.enter_context(patch.object(d.parent,'environment',return_value=self.environment))
        # The exact immutable ZIP has its own hash verifier; no provider/ZIP download is made by this test.
        stack.enter_context(patch.object(d,'verify_failure_zip'))
        stack.enter_context(patch.object(sys,'addaudithook'))
        stack.enter_context(patch('requests.Session',return_value=self.session))
        return stack
    def run(self, mode):
        with patch.object(sys,'argv',['diagnostic',mode,'--preflight-root',str(self.pre),'--output-root',str(self.output)]):
            with redirect_stdout(io.StringIO()): return runner.main()


class RegistrationTests(unittest.TestCase):
    def test_exact_failed_request_and_immutable_bytes(self):
        self.assertEqual(d.validate_inputs(ROOT),d.request())
        self.assertEqual(q.canonical_fingerprint(d.request()),d.REQUEST_SHA)
        self.assertEqual(d.request()['end_ns']-d.request()['start_ns'],650_000_001)
        self.assertEqual(d.contract()['request_index'],24)
        self.assertEqual(d.contract()['maximum_http_attempts'],3)
        self.assertEqual(len(d.IMMUTABLE_REFS),7)
        self.assertFalse(d.contract()['runtime_input_eligible'])

    def test_metadata_overestimate_does_not_relax_quote_ceiling(self):
        self.assertTrue(d.preflight(calls(),2,0)['preflight_passed'])
        for field,value in ((0,0),(0,d.MAX_BILLABLE_BYTES+1),(1,'0'),(1,'0.000016361476')):
            rows=calls();rows[field]['value']=value
            self.assertFalse(d.preflight(rows,2,0)['preflight_passed'])
        self.assertFalse(d.preflight(calls(),2,1)['preflight_passed'])
        self.assertFalse(d.preflight(calls()[:1],1,0)['preflight_passed'])

    def test_substitute_request_quote_and_window_rejected(self):
        rows=calls();rows[0]['request_content_sha256']='a'*64
        with self.assertRaises(ValueError):d.preflight(rows,2,0)
        for change in ('url','symbol','start','extra','limit','method'):
            with tempfile.TemporaryDirectory() as tmp:
                session=Session();t=DiagnosticHTTP(session=session,key='synthetic',temporary_root=Path(tmp))
                data=q.request_kwargs(d.request());data.update(symbols='JVA',stype_out='instrument_id')
                url='https://hist.databento.com/v0/metadata.get_billable_size'
                if change=='url':url='https://hist.databento.com/v0/batch.submit_job'
                if change=='symbol':data['symbols']='GITS'
                if change=='start':data['start']=q.request_kwargs({**d.request(),'start_ns':d.request()['start_ns']-1})['start']
                if change in ('extra','limit'):data[change]=1
                if change=='method':url='https://hist.databento.com/v0/metadata.get_record_count'
                with self.assertRaises(q.MetadataFailure):t.post(url,data,basic_auth=True)
                self.assertEqual(session.calls,[]);self.assertEqual(t.blocked,1)

    def test_execution_attempt_two_changed_tree_and_main_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/d.WORKFLOW_PATH;p.parent.mkdir(parents=True);p.write_bytes((ROOT/d.WORKFLOW_PATH).read_bytes())
            ex=d.execution_payload(code_commit='a'*40,code_tree='b'*40,workflow_sha256=d.file_sha(p),ci_run_id='123',validation_run_id='124')
            d.write_json(root/d.EXECUTION_PATH,ex)
            env={'EXECUTION_CODE_COMMIT_SHA':'a'*40,'EXECUTION_CODE_TREE_SHA':'b'*40,'GITHUB_SHA':'c'*40,
                'GITHUB_RUN_ID':'125','GITHUB_RUN_ATTEMPT':'1','GITHUB_REPOSITORY':'RoomyRems/momentumbot',
                'GITHUB_EVENT_NAME':'push','GITHUB_REF':'refs/heads/phase-3-historical-snapshot'}
            self.assertEqual(d.validate_execution(root,env),ex)
            for changed in ({'GITHUB_RUN_ATTEMPT':'2'},{'EXECUTION_CODE_TREE_SHA':'d'*40},{'GITHUB_REF':'refs/heads/main'}):
                with self.assertRaises(ValueError):d.validate_execution(root,{**env,**changed})

    def test_parent_failure_zip_substitution_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'wrong.zip'
            with zipfile.ZipFile(p,'w') as z:z.writestr('capture-report.json',(ROOT/d.FAILURE_REPORT_PATH).read_bytes())
            with self.assertRaisesRegex(ValueError,'ZIP differs'):d.verify_failure_zip(p,ROOT)

    def test_workflow_consumes_once_after_exact_parent_and_before_only_provider(self):
        workflow=yaml.load((ROOT/d.WORKFLOW_PATH).read_text(),Loader=yaml.BaseLoader)
        self.assertEqual(set(workflow['on']),{'push'})
        steps=workflow['jobs']['diagnose']['steps']
        providers=[i for i,s in enumerate(steps) if 'DATABENTO_API_KEY' in s.get('env',{})]
        self.assertEqual(len(providers),1)
        for name in ('Verify successful CI and dedicated validation at the exact code parent',
            'Verify the immutable failure artifact and parent refs','Durably upload consumption before provider access'):
            self.assertLess(next(i for i,s in enumerate(steps) if s.get('name')==name),providers[0])
        self.assertIn(d.CONSUMPTION_REF,steps[providers[0]-2]['run'])
        self.assertEqual(steps[-1]['if'],'always()')
        self.assertEqual(workflow['concurrency']['cancel-in-progress'],'false')
        self.assertIn('3.12.14',(ROOT/d.WORKFLOW_PATH).read_text())

    def test_unknown_text_is_hashed_and_arbitrary_errors_never_retained(self):
        text='synthetic private response'
        self.assertNotIn(text,json.dumps(d.scalar(text)))
        self.assertEqual(d.error_code(ValueError(text)),'unclassified_validation_exception')
        self.assertEqual(d.error_code(ValueError('missing exact request records')),'empty_exact_request')


@unittest.skipUnless(HAS_SDK,'real pinned SDK exercised by dedicated validation')
class NativeDiagnosticTests(unittest.TestCase):
    def observe(self, wire):
        import databento
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'raw.dbn';p.write_bytes(wire)
            native,nr=d.inspect_native_dbn(p)
            store=databento.DBNStore.from_file(p)
            try: mapped,mr=d.inspect_store(store,d.request())
            finally:store.reader.close()
        return native,nr,mapped,mr,d.observation_outcome(native,mapped,nr,mr)

    def test_compressed_metadata_only_has_no_native_or_mapped_records(self):
        n,nr,m,mr,o=self.observe(body())
        self.assertEqual(n['compression'],'zstd');self.assertEqual(n['native_record_count'],0)
        self.assertEqual(n['record_types'],{});self.assertEqual(nr,[]);self.assertEqual(mr,[])
        self.assertEqual(n['decoded_v3_record_bytes_sha256'],hashlib.sha256(b'').hexdigest())
        self.assertEqual(m['normalization_code'],'empty_exact_request')
        self.assertEqual(o['code'],'metadata_only_exact_dbn_empty_before_mapping')
        self.assertTrue(o['diagnostic_evidence_complete']);self.assertFalse(o['acquisition_gate_passed'])

    def test_empty_without_symbol_resolution_is_recorded_without_substituting_mapping(self):
        n,_,_,_,o=self.observe(body(mappings=False))
        self.assertEqual(n['metadata']['mappings'],[])
        self.assertEqual(n['metadata']['mapping_interval_count'],0)
        self.assertTrue(o['diagnostic_evidence_complete'])

    def test_nonempty_and_tied_records_preserve_native_fields_and_normalizer(self):
        n,nr,m,mr,o=self.observe(body(empty=False,duplicate=True))
        self.assertEqual(n['native_record_count'],2);self.assertEqual(n['native_mbp1_count'],2)
        self.assertEqual(nr[0]['fields'],nr[1]['fields']);self.assertEqual([r['index'] for r in nr],[0,1])
        self.assertEqual(m['normalization_code'],'passed')
        self.assertTrue(o['native_mapped_fields_identical']);self.assertTrue(o['diagnostic_evidence_complete'])
        self.assertFalse(o['runtime_input_eligible'])

    def test_uncompressed_fixture_uses_same_native_record_observation(self):
        n,_,_,_,o=self.observe(body(compressed=False))
        self.assertEqual(n['compression'],'none');self.assertTrue(o['diagnostic_evidence_complete'])

    def test_truncated_record_cannot_be_reported_as_empty(self):
        for wire in (body(empty=False,truncate=True),body(truncate=True)):
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp)/'truncated.dbn';p.write_bytes(wire)
                with self.assertRaises(Exception):d.inspect_native_dbn(p)

    def test_truncated_or_concatenated_compression_frames_are_not_empty_success(self):
        wire=body()
        for corrupt in (wire[:-1],wire+wire,wire+b'junk'):
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp)/'incomplete.dbn';p.write_bytes(corrupt)
                with self.assertRaises(Exception):d.inspect_native_dbn(p)

    def test_mismatched_symbol_and_nanosecond_bound_fail_exact_binding(self):
        for wire in (body(symbol='WRONG'),body(start_delta=-1)):
            n,_,m,_,o=self.observe(wire)
            self.assertFalse(n['metadata']['exact_request_metadata'])
            self.assertFalse(o['diagnostic_evidence_complete']);self.assertFalse(m['normalization_passed'])

    def test_decompression_bound_rejects_compression_bomb(self):
        import zstandard
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'large.dbn';p.write_bytes(zstandard.ZstdCompressor().compress(b'x'*4097))
            with patch.object(d,'MAX_PROJECTION_BYTES',4096):
                with self.assertRaisesRegex(ValueError,'decompression ceiling'):d.inspect_native_dbn(p)

    def test_exact_three_calls_empty_evidence_and_raw_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'out';out.mkdir();raw=root/'raw';raw.mkdir()
            session=Session(body());t=DiagnosticHTTP(session=session,key='synthetic',temporary_root=raw)
            result=runner.diagnose(t,out)
            self.assertTrue(result['diagnostic_evidence_complete']);self.assertEqual(result['error'],None)
            self.assertEqual(len(session.calls),3);self.assertEqual(list(raw.iterdir()),[])
            self.assertEqual(result['native_projection']['row_count'],0)
            self.assertEqual(result['projection']['uncompressed_sha256'],hashlib.sha256(b'').hexdigest())
            self.assertFalse(result['acquisition_gate_passed'])
            self.assertTrue(all(not opts['allow_redirects'] for _,opts in session.calls))
            with self.assertRaises(q.MetadataFailure):t.download()
            self.assertEqual(len(session.calls),3)

    def test_metadata_ceiling_failure_never_downloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            session=Session(size=d.MAX_BILLABLE_BYTES+1);t=DiagnosticHTTP(session=session,key='synthetic',temporary_root=Path(tmp))
            result=runner.diagnose(t,Path(tmp))
            self.assertEqual(len(session.calls),2);self.assertFalse(result['diagnostic_evidence_complete'])
            self.assertEqual(result['error'],'requote_unavailable_or_ceiling_exceeded')

    def test_http_error_sanitized_and_no_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            session=Session(status=503);t=DiagnosticHTTP(session=session,key='synthetic',temporary_root=Path(tmp))
            result=runner.diagnose(t,Path(tmp))
            self.assertEqual(len(session.calls),1);self.assertFalse(result['diagnostic_evidence_complete'])
            self.assertEqual(t.calls[0]['error'],'http_error');self.assertFalse(t.attempts[0]['status']=='pending')

    def test_oversized_partial_wire_retains_failure_ledger_and_removes_raw(self):
        with tempfile.TemporaryDirectory() as tmp:
            session=Session(b'x'*(d.MAX_WIRE_BYTES+1));t=DiagnosticHTTP(session=session,key='synthetic',temporary_root=Path(tmp))
            result=runner.diagnose(t,Path(tmp))
            self.assertEqual(result['error'],'response_too_large');self.assertFalse(result['diagnostic_evidence_complete'])
            self.assertEqual(t.attempts[-1]['status'],'failed');self.assertEqual(len(session.calls),3)
            self.assertFalse((Path(tmp)/'diagnostic.dbn.zst').exists())

    def test_complete_cli_requires_consumption_preserves_empty_evidence_and_verifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(Path(tmp),body())
            with h.context():
                with self.assertRaises(FileNotFoundError):h.run('--diagnose')
                self.assertEqual(h.session.calls,[])
                self.assertEqual(h.run('--consume'),0)
                self.assertEqual(h.run('--diagnose'),0)
                verified=d.verify_result(h.output,ROOT)
                self.assertEqual(verified['file_count'],17);self.assertEqual(verified['native_record_count'],0)
                self.assertFalse(verified['acquisition_gate_passed']);self.assertTrue(h.session.closed)
                self.assertNotIn('synthetic-test-key',''.join(p.read_text() for p in h.output.glob('*.json')))
                with self.assertRaisesRegex(ValueError,'write-once'):h.run('--diagnose')
                self.assertEqual(len(h.session.calls),3)

    def test_rehashed_report_inventory_and_ledger_tampering_rejected(self):
        for kind in ('gate','count','ledger','symbol','extra'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                h=Harness(Path(tmp),body())
                with h.context():
                    h.run('--consume');h.run('--diagnose')
                    if kind=='extra':(h.output/'extra.txt').write_text('unauthorized')
                    elif kind=='ledger':
                        p=h.output/'http-ledger.json';v=d.frozen(p);v['attempts'][-1]['request_content_sha256']='a'*64
                        d.write_json(p,d.seal({k:x for k,x in v.items() if k!='content_sha256'}),replace=True)
                    elif kind=='symbol':
                        p=h.output/'request.json';v=d.frozen(p);v['request']['symbols']=['WRONG']
                        d.write_json(p,d.seal({k:x for k,x in v.items() if k!='content_sha256'}),replace=True)
                    else:
                        p=h.output/'diagnostic-report.json';v=d.frozen(p)
                        if kind=='gate':v['acquisition_gate_passed']=True
                        else:v['projection']['row_count']=1
                        d.write_json(p,d.seal({k:x for k,x in v.items() if k!='content_sha256'}),replace=True)
                    rebuild_inventory(h.output)
                    with self.assertRaises(ValueError):d.verify_result(h.output,ROOT)

    def test_cli_malformed_native_preserves_failure_and_no_usable_tape(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(Path(tmp),body(empty=False,truncate=True))
            with h.context():
                h.run('--consume');self.assertEqual(h.run('--diagnose'),1)
                report=d.frozen(h.output/'diagnostic-report.json')
                self.assertFalse(report['diagnostic_evidence_complete']);self.assertFalse(report['raw_dbn_retained'])
                self.assertFalse(report['acquisition_gate_passed']);self.assertTrue(report['raw_temp_directory_removed'])
                self.assertEqual(len(h.session.calls),3)


if __name__=='__main__':unittest.main()
