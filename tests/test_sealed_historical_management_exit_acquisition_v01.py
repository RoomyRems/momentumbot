"""Provider-free exact management exit acquisition and evidence-verification regression."""
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from types import SimpleNamespace as N
import unittest
from unittest.mock import patch

import yaml
from momentumbot.research import sealed_historical_management_exit_acquisition_v01 as a
from momentumbot.research import sealed_historical_management_exit_transport_v01 as t
from momentumbot.research import sealed_historical_management_exit_quote_v01 as q

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import acquire_sealed_historical_management_exit_inputs_v01 as runner
HAS_SDK = importlib.util.find_spec('databento') is not None
REQUESTS, QUOTED = a.validate_inputs(ROOT)


def calls():
    return [{'ordinal':2*i+j+1,'request_id':r['request_id'],'request_content_sha256':q.canonical_fingerprint(r),
        'method':method,'status':'success','value':QUOTED['quote_rows'][i][field],'error':None}
        for i,r in enumerate(REQUESTS) for j,(method,field) in enumerate(zip(q.METHODS,('billable_size_bytes','quoted_cost_usd'),strict=True))]


def dbn_body(r, *, empty=False, delta=0, unmapped=False, duplicate=False, wrong_schema=False):
    import databento_dbn as dbn
    import zstandard
    day=date.fromisoformat(r['trading_date']);ns=r['start_ns']+1
    metadata=dbn.Metadata(dataset=r['dataset'],start=r['start_ns']+delta,end=r['end_ns'],
        stype_in=dbn.SType.RAW_SYMBOL,stype_out=dbn.SType.INSTRUMENT_ID,
        schema=dbn.Schema(('status' if r['schema']=='mbp-1' else 'mbp-1') if wrong_schema else r['schema']),symbols=r['symbols'],
        mappings=[] if unmapped else [N(raw_symbol=r['symbols'][0],intervals=[N(start_date=day,end_date=day+timedelta(days=1),symbol='1')])])
    raw=metadata.encode()
    if not empty:
        base={'publisher_id':2,'instrument_id':1,'ts_event':ns-1,'ts_recv':ns}
        if r['schema']=='status':msg=dbn.StatusMsg(**base,action=dbn.StatusAction.TRADING,is_trading=dbn.TriState.YES)
        else:msg=dbn.MBP1Msg(**base,price=1_000_000_000,size=10,action=dbn.Action.ADD,side=dbn.Side.BID,depth=0,
            sequence=1,levels=dbn.BidAskPair(bid_px=1_000_000_000,ask_px=1_010_000_000,bid_sz=10,ask_sz=20))
        raw+=bytes(msg)*(2 if duplicate else 1)
    return zstandard.ZstdCompressor().compress(raw)


class Response:
    def __init__(self,raw,status=200):self.raw,self.status_code=raw,status
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def iter_content(self,size):
        for i in range(0,len(self.raw),size):yield self.raw[i:i+size]


class Session:
    def __init__(self,*,empty=(),malformed=None,metadata_failure=False):
        self.calls=[];self.empty=set(empty);self.malformed=malformed;self.metadata_failure=metadata_failure;self.closed=False
    def post(self,url,**kwargs):
        index=len(self.calls);self.calls.append((url,kwargs))
        if index<160:
            raw=json.dumps(calls()[index]['value']).encode()
            return Response(raw,500 if self.metadata_failure and index==0 else 200)
        index-=160
        raw=self.malformed if index==0 and self.malformed is not None else dbn_body(REQUESTS[index],empty=index in self.empty)
        return Response(raw)
    def close(self):self.closed=True


class Harness:
    def __init__(self,base,**kwargs):
        self.output,self.pre=base/'output',base/'pre';self.pre.mkdir()
        self.execution_path=base/'execution.json'
        self.execution=a.execution_payload(code_commit='a'*40,code_tree='b'*40,
            workflow_sha256=a.file_sha(ROOT/a.WORKFLOW_PATH),ci_run_id='123',validation_run_id='124')
        a.write_json(self.execution_path,self.execution)
        self.env={'EXECUTION_CODE_COMMIT_SHA':'a'*40,'EXECUTION_CODE_TREE_SHA':'b'*40,'GITHUB_SHA':'c'*40,
            'GITHUB_RUN_ID':'125','GITHUB_RUN_ATTEMPT':'1','GITHUB_REPOSITORY':'RoomyRems/momentumbot',
            'GITHUB_EVENT_NAME':'push','GITHUB_REF':'refs/heads/phase-3-historical-snapshot','DATABENTO_API_KEY':'synthetic-test-key'}
        pins=dict(re.findall(r'^([A-Za-z0-9_.-]+)==([^\s\\]+)',(ROOT/q.LOCK_PATH).read_text(),re.M))
        self.environment=a.seal({'implementation':'CPython','python_version':'3.12.14','requirements_sha256':q.LOCK_SHA256,'package_versions':pins})
        self.parents=a.seal({'synthetic_already_verified_parent_fixture':True})
        (self.pre/'consumption-ref.json').write_text(json.dumps({'ref':a.CONSUMPTION_REF,'object':{'sha':'c'*40}}))
        for name in a.PARENT_ARTIFACTS:(self.pre/name).write_bytes(b'synthetic immutable parent ZIP fixture')
        self.session=Session(**kwargs)
    def context(self):
        stack=ExitStack()
        stack.enter_context(patch.dict(os.environ,self.env,clear=True))
        stack.enter_context(patch.object(a,'EXECUTION_PATH',str(self.execution_path)))
        stack.enter_context(patch.object(a,'environment',return_value=self.environment))
        # External immutable ZIP verification is separately exercised against measured artifacts.
        # Only that boundary is replaced; all new HTTP, SDK, ledgers and output verification are real.
        stack.enter_context(patch.object(a,'verify_parents',return_value=self.parents))
        stack.enter_context(patch.object(sys,'addaudithook'))
        stack.enter_context(patch('requests.Session',return_value=self.session))
        stack.enter_context(patch.object(t.time,'sleep',return_value=None))
        for cls in (t.MetadataOnlyHTTP,t.ExactTimeseriesHTTP):
            original=cls.__init__
            def init(self,*args,_original=original,**kwargs):kwargs['pause']=lambda _:None;_original(self,*args,**kwargs)
            stack.enter_context(patch.object(cls,'__init__',init))
        return stack
    def run(self,mode):
        with patch.object(sys,'argv',['acquire',mode,'--preflight-root',str(self.pre),'--output-root',str(self.output)]),redirect_stdout(io.StringIO()):
            return runner.main()


def reseal(path,value):a.write_json(path,a.seal({k:v for k,v in value.items() if k!='content_sha256'}),replace=True)


class RegistrationTests(unittest.TestCase):
    def test_frozen_exit_parent_bytes_and_gate_flags(self):
        self.assertEqual(a.validate_inputs(ROOT)[0],REQUESTS)
        self.assertEqual(q.canonical_fingerprint(REQUESTS),a.REQUEST_LIST_SHA)
        self.assertEqual(REQUESTS[0]['request_id'],'2025-05-30-GITS-mbp-1')
        self.assertEqual(len(a.IMMUTABLE_REFS),16)
        self.assertEqual(a.contract()['maximum_http_attempts'],240)
        self.assertFalse(a.contract()['acquisition_gate_passed'])

    def test_original_or_substituted_requests_rejected(self):
        for rows in (REQUESTS[:-1],REQUESTS[::-1],a.native_parent.parent.validate_inputs(ROOT)[0]):
            with self.assertRaises(ValueError):a.validate_requests(rows)
        rows=deepcopy(REQUESTS);rows[0]['end_ns']+=1
        with self.assertRaises(ValueError):a.validate_requests(rows)

    def test_every_original_quote_ceiling_is_required(self):
        self.assertTrue(a.preflight(REQUESTS,QUOTED,calls(),160,0)['preflight_passed'])
        for index,value in ((0,0),(0,calls()[0]['value']+1),(1,'1')):
            values=calls();values[index]['value']=value
            self.assertFalse(a.preflight(REQUESTS,QUOTED,values,160,0)['preflight_passed'])
        self.assertFalse(a.preflight(REQUESTS,QUOTED,calls()[:-1],159,0)['preflight_passed'])
        self.assertFalse(a.preflight(REQUESTS,QUOTED,calls(),160,1)['preflight_passed'])
        values=calls();values[1]['request_content_sha256']='f'*64
        with self.assertRaises(ValueError):a.preflight(REQUESTS,QUOTED,values,160,0)

    def test_quote_reseal_cannot_replace_original(self):
        quoted=deepcopy(QUOTED);quoted['quote_rows'][0]['billable_size_bytes']+=1
        quoted=q.seal({k:v for k,v in quoted.items() if k!='content_sha256'})
        with self.assertRaises(ValueError):a.preflight(REQUESTS,quoted,calls(),160,0)

    def test_individual_ceiling_cannot_be_offset_by_another_request(self):
        for field in ('size','cost'):
            values=calls()
            if field=='size':
                values[0]['value']+=1;values[2]['value']-=1
            else:
                for index,delta in ((1,Decimal('0.000000000001')),(3,Decimal('-0.000000000001'))):
                    values[index]['value']=format(Decimal(values[index]['value'])+delta,'f')
            result=a.preflight(REQUESTS,QUOTED,values,160,0)
            self.assertEqual(result['total_billable_bytes'],a.MAX_BILLABLE_BYTES)
            self.assertEqual(Decimal(result['total_quoted_cost_usd']),Decimal(a.MAX_COST_USD))
            self.assertFalse(result['preflight_passed'])

    def test_native_decoder_and_normalizer_remain_original_functions(self):
        self.assertIs(a.native_summary,a.native_parent.native_summary)
        self.assertIs(a.validate_native_observation,a.native_parent.validate_native_observation)
        self.assertIs(a.tape_records,a.native_parent.tape_records)
        self.assertIs(a.parent.normalize,a.native_parent.parent.normalize)

    def test_rehashed_limits_cannot_change_individual_caps(self):
        original=a.frozen
        limits=deepcopy(original(ROOT/a.LIMITS_PATH))
        limits['request_limits'][0]['maximum_wire_bytes']+=1
        limits=a.seal({k:v for k,v in limits.items() if k!='content_sha256'})
        def read(path):return limits if path==ROOT/a.LIMITS_PATH else original(path)
        with patch.object(a,'frozen',side_effect=read):
            with self.assertRaises(ValueError):a.validate_inputs(ROOT)

    def test_http_ledger_rehashed_boolean_and_wire_substitutions_rejected(self):
        attempt={'ordinal':1,'request_id':REQUESTS[0]['request_id'],
            'request_content_sha256':q.canonical_fingerprint(REQUESTS[0]),
            'method':'timeseries.get_range','status':'complete','http_status':200,
            'wire_bytes':100,'maximum_wire_bytes':200}
        ledger={'http_attempts':1,'blocked_attempts':0,'attempts':[attempt],
            'automatic_retries':0,'redirects_followed':0,'unregistered_endpoint_calls':0}
        a.validate_http_ledger(a.seal(ledger),metadata=False)
        for field in ('http_attempts','blocked_attempts','automatic_retries','redirects_followed'):
            changed=deepcopy(ledger);changed[field]=bool(changed[field])
            with self.assertRaises(ValueError):a.validate_http_ledger(a.seal(changed),metadata=False)
        for change in ({'ordinal':True},{'wire_bytes':True},{'maximum_wire_bytes':True},
            {'wire_bytes':201},{'wire_bytes':0},{'http_status':True},{'extra':0}):
            changed=deepcopy(ledger);changed['attempts'][0].update(change)
            with self.assertRaises(ValueError):a.validate_http_ledger(a.seal(changed),metadata=False)

    def test_transport_reuses_immutable_bounded_methods(self):
        from momentumbot.research.sealed_historical_metadata_transport_v01 import MetadataOnlyHTTP
        from momentumbot.research.sealed_historical_execution_transport_v01 import ExactTimeseriesHTTP
        self.assertIs(t.MetadataOnlyHTTP.post,MetadataOnlyHTTP.post)
        self.assertIs(t.ExactTimeseriesHTTP.stream,ExactTimeseriesHTTP.stream)
        self.assertEqual(len(t.MetadataOnlyHTTP(REQUESTS,session=None,key='test').expected),160)
        with tempfile.TemporaryDirectory() as tmp:
            bad=a.preflight(REQUESTS,QUOTED,calls()[:-1],159,0)
            with self.assertRaises(ValueError):t.ExactTimeseriesHTTP(REQUESTS,QUOTED,bad,session=None,key='test',temporary_root=Path(tmp))

    def test_unregistered_metadata_endpoint_window_and_body_blocked(self):
        for changed in ('url','start','symbol','limit','method'):
            session=N(post=lambda *a,**kw: (_ for _ in ()).throw(AssertionError('provider touched')))
            transport=t.MetadataOnlyHTTP(REQUESTS,session=session,key='test',pause=lambda _:None)
            data=q.request_kwargs(REQUESTS[0]);data.update(symbols=REQUESTS[0]['symbols'][0],stype_out='instrument_id')
            url='https://hist.databento.com/v0/metadata.get_billable_size'
            if changed=='url':url='https://hist.databento.com/v0/batch.submit_job'
            if changed=='start':data['start']=q.request_kwargs({**REQUESTS[0],'start_ns':REQUESTS[0]['start_ns']-1})['start']
            if changed=='symbol':data['symbols']='OTHER'
            if changed=='limit':data['limit']=1
            if changed=='method':url='https://hist.databento.com/v0/metadata.get_record_count'
            with self.assertRaises(q.MetadataFailure):transport.post(url,data,basic_auth=True)
            self.assertEqual(transport.blocked,1);self.assertEqual(transport.attempts,[])

    def test_execution_requires_attempt_one_exact_parent_and_research_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(Path(tmp));root=Path(tmp);p=root/a.WORKFLOW_PATH;p.parent.mkdir(parents=True);p.write_bytes((ROOT/a.WORKFLOW_PATH).read_bytes())
            with patch.object(a,'EXECUTION_PATH',str(h.execution_path)):
                self.assertEqual(a.validate_execution(root,h.env),h.execution)
                for change in ({'GITHUB_RUN_ATTEMPT':'2'},{'GITHUB_REF':'refs/heads/main'},{'EXECUTION_CODE_TREE_SHA':'d'*40}):
                    with self.assertRaises(ValueError):a.validate_execution(root,{**h.env,**change})

    def test_substituted_parent_artifacts_block_before_acquisition(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            for name in a.PARENT_ARTIFACTS:(base/name).write_bytes(b'wrong')
            with self.assertRaises(ValueError):a.verify_parents(base,ROOT)

    def test_coverage_never_drops_unattempted_exit_requests(self):
        rows=a.coverage([],ROOT)
        self.assertEqual(len(rows),80)
        self.assertEqual(sum(r['status']=='unattempted' for r in rows),80)
        self.assertTrue(all(r['runtime_input_eligible'] is False for r in rows))
        self.assertEqual([r['exit_request_index'] for r in rows],list(range(80)))

    def test_workflow_consumes_after_parent_checks_before_only_provider(self):
        w=yaml.load((ROOT/a.WORKFLOW_PATH).read_text(),Loader=yaml.BaseLoader)
        self.assertEqual(set(w['on']),{'push'});self.assertEqual(w['concurrency']['cancel-in-progress'],'false')
        steps=w['jobs']['acquire']['steps'];providers=[i for i,s in enumerate(steps) if 'DATABENTO_API_KEY' in s.get('env',{})]
        self.assertEqual(len(providers),1)
        for name in ('Verify successful CI and dedicated validation at the exact code parent',
            'Verify both immutable retained parent artifacts and protected refs','Durably upload consumption before provider access'):
            self.assertLess(next(i for i,s in enumerate(steps) if s.get('name')==name),providers[0])
        self.assertIn(a.CONSUMPTION_REF,steps[providers[0]-2]['run'])
        self.assertEqual(steps[-1]['if'],'always()')


@unittest.skipUnless(HAS_SDK,'real pinned SDK exercised by dedicated validation')
class NativeTests(unittest.TestCase):
    def test_timeseries_window_route_path_and_exhausted_scope_block_before_network(self):
        for change in ('url','end','symbol','limit','path','exhausted'):
            with tempfile.TemporaryDirectory() as tmp:
                session=N(post=lambda *args,**kw: (_ for _ in ()).throw(AssertionError('provider touched')))
                transport=t.ExactTimeseriesHTTP(REQUESTS,QUOTED,a.preflight(REQUESTS,QUOTED,calls(),160,0),
                    session=session,key='test',temporary_root=Path(tmp),pause=lambda _:None)
                data=q.request_kwargs(REQUESTS[0]);data.update(symbols=REQUESTS[0]['symbols'][0],
                    stype_out='instrument_id',encoding='dbn',compression='zstd')
                url='https://hist.databento.com/v0/timeseries.get_range';path=Path(tmp)/'request-000.dbn.zst'
                if change=='url':url='https://hist.databento.com/v0/batch.submit_job'
                if change=='end':data['end']=q.request_kwargs({**REQUESTS[0],'end_ns':REQUESTS[0]['end_ns']+1})['end']
                if change=='symbol':data['symbols']='OTHER'
                if change=='limit':data['limit']=1
                if change=='path':path=Path(tmp)/'other.dbn.zst'
                if change=='exhausted':transport.attempts=[{}]*80
                with self.assertRaises(q.MetadataFailure):transport.stream(url,data,True,path)
                self.assertEqual(transport.blocked,1)
                self.assertEqual(len(transport.attempts),80 if change=='exhausted' else 0)

    def test_real_nonempty_and_metadata_only_both_schemas(self):
        from databento import DBNStore
        for r in REQUESTS[:2]:
            for empty in (False,True):
                with tempfile.TemporaryDirectory() as tmp:
                    p=Path(tmp)/'input.dbn.zst';p.write_bytes(dbn_body(r,empty=empty))
                    native=a.native_summary(p,r,1000000)
                    self.assertEqual(native['native_record_count'],0 if empty else 1)
                    store=DBNStore.from_file(p)
                    try:
                        if empty:
                            with self.assertRaisesRegex(ValueError,'missing exact request records'):a.parent.normalize(store,r)
                        else:self.assertEqual(len(a.parent.normalize(store,r)),1)
                    finally:store.reader.close()

    def test_truncated_or_concatenated_zstd_is_not_empty_evidence(self):
        raw=dbn_body(REQUESTS[0],empty=True)
        for wire in (raw[:-1],raw+b'trailing',raw+raw):
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp)/'input';p.write_bytes(wire)
                with self.assertRaises(Exception):a.native_summary(p,REQUESTS[0],1000000)

    def test_truncated_uncompressed_native_record_rejected(self):
        import zstandard
        wire=zstandard.ZstdDecompressor().decompress(dbn_body(REQUESTS[0]))[:-1]
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'input';p.write_bytes(wire)
            with self.assertRaises(Exception):a.native_summary(p,REQUESTS[0],1000000)

    def test_wrong_metadata_or_missing_mapping_is_not_unavailable(self):
        for change in ({'delta':1},{'unmapped':True},{'wrong_schema':True}):
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp)/'input';p.write_bytes(dbn_body(REQUESTS[0],empty=True,**change))
                with self.assertRaises(ValueError):a.native_summary(p,REQUESTS[0],1000000)

    def test_resealed_native_mapping_and_noninteger_count_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'input';path.write_bytes(dbn_body(REQUESTS[0],empty=True))
            native=a.native_summary(path,REQUESTS[0],1000000)
            for change in ({'native_record_count':False},{'mapping_intervals':[]},{'wire_sha256':'bad'}):
                changed=a.seal({k:v for k,v in {**native,**change}.items() if k!='content_sha256'})
                with self.assertRaises(ValueError):a.validate_native_observation(changed,REQUESTS[0],1000000)

    def test_advertised_native_decompression_bomb_rejected_before_decode(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'input';path.write_bytes(dbn_body(REQUESTS[0],empty=True))
            with patch('zstandard.frame_content_size',return_value=a.MAX_NATIVE_BYTES+1):
                with self.assertRaisesRegex(ValueError,'decompression ceiling'):a.native_summary(path,REQUESTS[0],1000000)

    def test_wire_ceiling_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'input';p.write_bytes(dbn_body(REQUESTS[0],empty=True))
            with self.assertRaises(ValueError):a.native_summary(p,REQUESTS[0],1)
            link=Path(tmp)/'link';link.symlink_to(p)
            with self.assertRaises(ValueError):a.native_summary(link,REQUESTS[0],1000000)

    def test_equal_native_quote_keys_keep_original_ordinal(self):
        from databento import DBNStore
        r=REQUESTS[0]
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'input';p.write_bytes(dbn_body(r,duplicate=True))
            store=DBNStore.from_file(p)
            try:
                records=a.parent.normalize(store,r)
                self.assertEqual(a.native_summary(p,r,1000000)['native_record_count'],2)
                self.assertEqual([r['source_record_index'] for r in records],[0,1])
                self.assertEqual(a.parent.normalization_summary(records,r)['native_key_adjacent_ties'],1)
            finally:store.reader.close()


@unittest.skipUnless(HAS_SDK,'real pinned SDK exercised by dedicated validation')
class EndToEndTests(unittest.TestCase):
    def test_missing_credential_preserves_zero_call_failure_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(Path(tmp));h.env.pop('DATABENTO_API_KEY')
            with h.context():
                h.run('--consume');self.assertEqual(h.run('--acquire'),1)
                self.assertEqual(h.session.calls,[])
                self.assertEqual(a.frozen(h.output/'capture-report.json')['error'],'credential_missing')
                self.assertEqual(a.verify_capture(h.output,ROOT)['unattempted_count'],80)

    def test_failed_temporary_cleanup_cannot_report_complete_evidence(self):
        original=tempfile.TemporaryDirectory
        class CleanupFailure(original):
            def __exit__(self,*args):
                super().__exit__(*args)
                raise OSError('synthetic cleanup failure')
        with original() as tmp:
            h=Harness(Path(tmp))
            with h.context():
                h.run('--consume')
                with patch.object(runner.tempfile,'TemporaryDirectory',CleanupFailure):
                    self.assertEqual(h.run('--acquire'),1)
                report=a.frozen(h.output/'capture-report.json')
                self.assertFalse(report['raw_temp_directory_removed'])
                self.assertFalse(report['request_evidence_complete'])
                self.assertEqual(report['error'],'acquisition_runtime_failed')
                self.assertEqual(report['new_complete_count'],80)
                self.assertFalse(a.verify_capture(h.output,ROOT)['request_evidence_complete'])

    def test_complete_exit_capture_retains_empty_outcomes_and_closes_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(Path(tmp),empty=(0,1,10))
            with h.context():
                self.assertEqual(h.run('--consume'),0);self.assertEqual(h.session.calls,[])
                self.assertEqual(h.run('--acquire'),0)
                verified=a.verify_capture(h.output,ROOT,require_complete=True)
                self.assertEqual(verified['new_complete_count'],77)
                self.assertEqual(verified['new_unavailable_count'],3)
                self.assertEqual(verified['http_attempts'],240)
                self.assertFalse(verified['acquisition_gate_passed'])
                self.assertFalse((h.output/'tapes/request-000.jsonl.gz').exists())
                for name in a.PARENT_ARTIFACTS:self.assertEqual((h.pre/name).read_bytes(),(h.output/name).read_bytes())
                report=a.frozen(h.output/'capture-report.json')
                self.assertEqual(len(report['coverage']),80)
                self.assertEqual(len(report['original_opportunities']),109)
                self.assertEqual(sum(o['entry_input_status']=='unavailable' for o in report['original_opportunities']),23)
                self.assertNotIn('synthetic-test-key',json.dumps(report))
                self.assertTrue(h.session.closed)
                with self.assertRaises(ValueError):h.run('--acquire')
                self.assertEqual(len(h.session.calls),240)
                path=h.output/'timeseries-http-ledger.json';original=path.read_bytes()
                for change in ({'ordinal':True},{'wire_bytes':True},{'wire_bytes':99999}):
                    ledger=a.frozen(path);ledger['attempts'][0].update(change);reseal(path,ledger)
                    a.write_inventory(h.output,report,replace=True)
                    with self.assertRaises(ValueError):a.verify_capture(h.output,ROOT)
                    path.write_bytes(original)
                a.write_inventory(h.output,report,replace=True)

    def test_missing_consumption_blocks_provider_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(Path(tmp))
            with h.context():
                with self.assertRaises(FileNotFoundError):h.run('--acquire')
                self.assertEqual(h.session.calls,[])

    def test_metadata_failure_prevents_all_downloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(Path(tmp),metadata_failure=True)
            with h.context():
                h.run('--consume');self.assertEqual(h.run('--acquire'),1)
                self.assertEqual(len(h.session.calls),160)
                result=a.verify_capture(h.output,ROOT)
                self.assertEqual(result['unattempted_count'],80)
                self.assertFalse(result['request_evidence_complete'])

    def test_malformed_first_native_response_stops_and_retains_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(Path(tmp),malformed=dbn_body(REQUESTS[0],empty=True,delta=1))
            with h.context():
                h.run('--consume');self.assertEqual(h.run('--acquire'),1)
                self.assertEqual(len(h.session.calls),161)
                verified=a.verify_capture(h.output,ROOT)
                self.assertEqual(verified['unattempted_count'],79)
                row=a.frozen(h.output/'capture-report.json')['requests'][0]
                self.assertEqual(row['failure_stage'],'native_validation');self.assertIsNone(row['unavailable'])

    def test_partial_tape_write_is_retained_ineligible_and_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(Path(tmp))
            def fail(path,*args,**kwargs):path.write_bytes(b'partial normalized evidence');raise OSError('synthetic-sensitive-error')
            with h.context(),patch.object(a.parent,'write_tape',side_effect=fail):
                h.run('--consume');self.assertEqual(h.run('--acquire'),1)
                verified=a.verify_capture(h.output,ROOT)
                self.assertFalse(verified['request_evidence_complete'])
                row=a.frozen(h.output/'capture-report.json')['requests'][0]
                self.assertEqual(row['failure_stage'],'normalized_tape_write')
                self.assertEqual(len(row['partial']),1);self.assertFalse(row['partial'][0]['runtime_input_eligible'])
                self.assertNotIn('synthetic-sensitive-error',json.dumps(row))

    def test_partial_receipt_preserves_completed_tape_as_ineligible(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(Path(tmp));original=a.write_json
            def fail(path,value,**kw):
                if path==h.output/'receipts/request-000.json':path.write_bytes(b'partial receipt');raise OSError('synthetic')
                return original(path,value,**kw)
            with h.context(),patch.object(a,'write_json',side_effect=fail):
                h.run('--consume');self.assertEqual(h.run('--acquire'),1)
                row=a.frozen(h.output/'capture-report.json')['requests'][0]
                self.assertEqual(row['failure_stage'],'receipt_write');self.assertEqual(len(row['partial']),2)
                self.assertFalse(a.verify_capture(h.output,ROOT)['request_evidence_complete'])

    def test_rehashed_gate_population_and_receipt_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(Path(tmp),empty=(0,))
            with h.context():
                h.run('--consume');self.assertEqual(h.run('--acquire'),0)
                report_path=h.output/'capture-report.json';original=report_path.read_bytes()
                for change in ({'acquisition_gate_passed':True},{'new_unavailable_count':0},{'original_date_count':29}):
                    report=a.frozen(report_path);report.update(change);reseal(report_path,report)
                    a.write_inventory(h.output,a.frozen(report_path),replace=True)
                    with self.assertRaises(ValueError):a.verify_capture(h.output,ROOT)
                    report_path.write_bytes(original)
                a.write_inventory(h.output,a.frozen(report_path),replace=True)
                receipt=h.output/'receipts/request-000.json';value=a.frozen(receipt)
                value['completion']['unavailable']['runtime_input_eligible']=True;reseal(receipt,value)
                a.write_inventory(h.output,a.frozen(report_path),replace=True)
                with self.assertRaises(ValueError):a.verify_capture(h.output,ROOT)

    def test_rehashed_tape_mutation_and_extra_member_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(Path(tmp))
            with h.context():
                h.run('--consume');self.assertEqual(h.run('--acquire'),0)
                path=h.output/'tapes/request-000.jsonl.gz';original=path.read_bytes();path.write_bytes(original[:-1])
                a.write_inventory(h.output,a.frozen(h.output/'capture-report.json'),replace=True)
                with self.assertRaises(Exception):a.verify_capture(h.output,ROOT)
                path.write_bytes(original);(h.output/'unexpected.bin').write_bytes(b'extra')
                a.write_inventory(h.output,a.frozen(h.output/'capture-report.json'),replace=True)
                with self.assertRaises(ValueError):a.verify_capture(h.output,ROOT)
