from __future__ import annotations

from copy import deepcopy
import gzip
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
import yaml

from momentumbot.research import sealed_historical_execution_diagnostic_v01 as d
from momentumbot.research import sealed_historical_execution_quote_v01 as q
from momentumbot.research.sealed_historical_execution_diagnostic_transport_v01 import DiagnosticHTTP

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from diagnose_sealed_historical_execution_inputs_v01 import diagnose

HAS_SDK = importlib.util.find_spec('databento') is not None


class Store:
    def __init__(self, rows=None):
        r = d.request()
        self.metadata = {k:r[k] for k in ('dataset','schema','stype_in','symbols')}
        self.metadata.update(start=r['start_ns'],end=r['end_ns'])
        self.rows = rows if rows is not None else [{'symbol':'GITS','ts_recv':r['start_ns']+1,
            'sequence':1,'bid_px_00':1_000_000_000,'bid_sz_00':10,'ask_px_00':1_010_000_000,'ask_sz_00':20}]

    def to_df(self, **kwargs):
        return pd.DataFrame(self.rows)


class Response:
    def __init__(self, body, status=200):
        self.body, self.status_code = body,status
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def iter_content(self,size):
        for index in range(0,len(self.body),size):
            yield self.body[index:index+size]


class Session:
    def __init__(self, bodies, status=200):
        self.bodies, self.status, self.calls = bodies,status,[]
    def post(self,url,**kwargs):
        self.calls.append((url,kwargs))
        return Response(self.bodies[len(self.calls)-1],self.status)


def calls(size=d.MAX_BILLABLE_BYTES,cost=d.MAX_COST_USD):
    return [{'ordinal':i+1,'method':method,'request_content_sha256':d.REQUEST_SHA,
             'status':'success','value':value,'error':None}
            for i,(method,value) in enumerate(zip(q.METHODS,(size,cost),strict=True))]


def metadata_data(method):
    r=d.request(); data=q.request_kwargs(r)
    data.update(symbols='GITS',stype_out='instrument_id')
    return 'https://hist.databento.com/v0/metadata.'+method,data


def dbn_bytes(duplicate=False):
    import databento_dbn as dbn
    from datetime import date,timedelta
    from types import SimpleNamespace as N
    r=d.request();day=date.fromisoformat(r['trading_date']);ns=r['start_ns']+1
    metadata=dbn.Metadata(dataset='XNAS.ITCH',start=r['start_ns'],end=r['end_ns'],
        stype_in=dbn.SType.RAW_SYMBOL,stype_out=dbn.SType.INSTRUMENT_ID,schema=dbn.Schema.MBP_1,
        symbols=['GITS'],mappings=[N(raw_symbol='GITS',intervals=[N(start_date=day,end_date=day+timedelta(days=1),symbol='1')])])
    msg=dbn.MBP1Msg(publisher_id=2,instrument_id=1,ts_event=ns-1,price=1_000_000_000,size=10,
        action=dbn.Action.ADD,side=dbn.Side.BID,depth=0,ts_recv=ns,sequence=1,
        levels=dbn.BidAskPair(bid_px=1_000_000_000,ask_px=1_010_000_000,bid_sz=10,ask_sz=20))
    return metadata.encode()+bytes(msg)*(2 if duplicate else 1)


class DiagnosticTests(unittest.TestCase):
    def test_exact_failure_and_frozen_parent_chain(self):
        self.assertEqual(d.validate_inputs(ROOT),d.request())
        self.assertEqual(q.canonical_fingerprint(d.request()),d.REQUEST_SHA)
        self.assertNotEqual(d.CONSUMPTION_REF,d.parent.CONSUMPTION_REF)
        self.assertFalse(d.contract()['runtime_input_eligible'])

    def test_size_cost_zero_or_incomplete_preflight_blocks(self):
        for rows in (calls(size=0),calls(size=d.MAX_BILLABLE_BYTES+1),calls(cost='0.002208173276'),calls()[:1]):
            self.assertFalse(d.preflight(rows,len(rows),0)['preflight_passed'])
        self.assertFalse(d.preflight(calls(),2,1)['preflight_passed'])
        self.assertTrue(d.preflight(calls(),2,0)['preflight_passed'])

    def test_request_substitution_cannot_pass_preflight_or_inspection(self):
        rows=calls();rows[0]['request_content_sha256']='a'*64
        with self.assertRaises(ValueError):d.preflight(rows,2,0)
        r=d.request();r['end_ns']+=1
        with self.assertRaises(ValueError):d.inspect_store(Store(),r)

    def test_metadata_failure_codes_are_exact_and_do_not_rewrite_fields(self):
        for field,value,code in [('start',d.request()['start_ns']-1,'metadata_start_mismatch'),
            ('end',d.request()['end_ns']+1,'metadata_end_mismatch'),('schema','status','metadata_schema_mismatch'),
            ('dataset','WRONG','metadata_dataset_mismatch'),('stype_in','instrument_id','metadata_stype_mismatch'),
            ('symbols',['WRONG'],'metadata_symbols_mismatch')]:
            with self.subTest(field=field):
                store=Store();store.metadata[field]=value
                observed,rows=d.inspect_store(store,d.request())
                self.assertEqual(observed['normalization_code'],code)
                self.assertFalse(observed['normalization_passed'])
                self.assertEqual(len(rows),1)
                self.assertEqual(store.metadata[field],value)

    def test_nanosecond_receive_bounds_remain_exclusive(self):
        for ns in (d.request()['start_ns']-1,d.request()['end_ns']):
            store=Store();store.rows[0]['ts_recv']=ns
            observed,rows=d.inspect_store(store,d.request())
            self.assertEqual(observed['normalization_code'],'record_outside_request')
            self.assertEqual(rows[0]['fields']['ts_recv']['value'],ns)

    def test_duplicate_and_descending_quote_keys_retained_in_original_order(self):
        for delta in (0,-1):
            first=Store().rows[0];second={**first,'ts_recv':first['ts_recv']+delta}
            observed,rows=d.inspect_store(Store([first,second]),d.request())
            self.assertEqual(observed['normalization_code'],'quote_order_not_strict')
            self.assertTrue(observed['normalizer_layer_passed'])
            self.assertEqual(observed['order_observation']['first']['row_index'],1)
            self.assertEqual(observed['order_observation']['first']['equal_key'],delta==0)
            self.assertEqual([r['fields']['ts_recv']['value'] for r in rows],[first['ts_recv'],second['ts_recv']])

    def test_equal_receive_time_increasing_sequence_is_preserved(self):
        first=Store().rows[0];second={**first,'sequence':2}
        observed,rows=d.inspect_store(Store([first,second]),d.request())
        self.assertTrue(observed['normalization_passed'])
        self.assertEqual(observed['order_observation']['non_strict_adjacent_count'],0)
        self.assertFalse(observed['runtime_input_eligible'])
        self.assertEqual(len(rows),2)

    def test_crossed_and_undefined_books_are_not_filtered_or_repaired(self):
        for ask in (1,2**63-1):
            store=Store();store.rows[0]['ask_px_00']=ask
            observed,rows=d.inspect_store(store,d.request())
            self.assertTrue(observed['normalization_passed'])
            self.assertEqual(rows[0]['fields']['ask_px_00']['value'],ask)

    def test_field_and_integer_failures_remain_explicit(self):
        store=Store();del store.rows[0]['sequence']
        observed,_=d.inspect_store(store,d.request())
        self.assertEqual(observed['normalization_code'],'mapped_frame_schema_fields_missing')
        self.assertEqual(observed['frame']['missing_required_fields'],['sequence'])
        store=Store();store.rows[0]['bid_px_00']=1.5
        observed,rows=d.inspect_store(store,d.request())
        self.assertEqual(observed['normalization_code'],'bid_px_00_invalid_integer')
        self.assertEqual(rows[0]['fields']['bid_px_00'],{'kind':'other_type'})

    def test_unknown_text_and_exception_details_cannot_escape(self):
        secret='synthetic-sensitive-provider-message'
        store=Store();store.rows[0]['symbol']=secret;store.metadata['dataset']=secret
        observed,rows=d.inspect_store(store,d.request())
        self.assertNotIn(secret,json.dumps([observed,rows]))
        self.assertNotIn(secret,d.error_code(ValueError(secret)))
        with patch.object(Store,'to_df',side_effect=RuntimeError(secret)):
            observed,_=d.inspect_store(Store(),d.request())
        self.assertEqual(observed['normalization_code'],'record_mapping_failed')
        self.assertNotIn(secret,json.dumps(observed))

    def test_projection_determinism_content_hash_and_retention_ceiling(self):
        observed,rows=d.inspect_store(Store(),d.request())
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'one.gz';other=Path(tmp)/'two.gz'
            one=d.write_projection(path,rows);two=d.write_projection(other,rows)
            self.assertEqual(one,two)
            decoded=[json.loads(line) for line in gzip.decompress(path.read_bytes()).splitlines()]
            self.assertEqual(q.canonical_fingerprint(decoded),observed['projection_content_sha256'])
            with patch.object(d,'MAX_PROJECTION_BYTES',1),self.assertRaises(ValueError):
                d.write_projection(Path(tmp)/'limited.gz',rows)

    def test_projection_row_limit_is_explicit(self):
        with patch.object(d,'MAX_ROWS',0):
            observed,rows=d.inspect_store(Store(),d.request())
        self.assertFalse(observed['frame']['mapping_passed'])
        self.assertEqual(observed['frame']['code'],'row_ceiling_exceeded')
        self.assertEqual(rows,[])

    def test_metadata_http_error_stops_without_retry_and_journals_before_io(self):
        with tempfile.TemporaryDirectory() as tmp:
            states=[];session=Session([b'forbidden response must not persist'],status=302)
            transport=DiagnosticHTTP(session=session,key='synthetic',temporary_root=Path(tmp),progress=lambda x:states.append(deepcopy(x)))
            url,data=metadata_data('get_billable_size')
            with self.assertRaises(q.MetadataFailure):transport.post(url,data,basic_auth=True)
            self.assertEqual(len(session.calls),1)
            self.assertEqual(states[0]['attempts'][0]['status'],'pending')
            self.assertEqual(transport.calls[0]['error'],'http_error')
            self.assertNotIn('forbidden response',json.dumps(transport.ledger()))
            self.assertFalse(session.calls[0][1]['allow_redirects'])

    def test_forbidden_endpoint_symbol_and_window_are_rejected_before_io(self):
        for change in ('url','symbol','start','extra'):
            with tempfile.TemporaryDirectory() as tmp:
                session=Session([]);transport=DiagnosticHTTP(session=session,key='synthetic',temporary_root=Path(tmp))
                url,data=metadata_data('get_billable_size')
                if change=='url':url='https://hist.databento.com/v0/batch.submit_job'
                if change=='symbol':data['symbols']='OTHER'
                if change=='start':data['start']=q.request_kwargs({**d.request(),'start_ns':d.request()['start_ns']-1})['start']
                if change=='extra':data['limit']=1
                with self.assertRaises(q.MetadataFailure):transport.post(url,data,basic_auth=True)
                self.assertEqual(session.calls,[])
                self.assertEqual(transport.blocked,1)

    @unittest.skipUnless(HAS_SDK,'pinned SDK covered by dedicated diagnostic validation')
    def test_actual_sdk_end_to_end_failed_order_retains_diagnostic_and_cleans_raw(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'out';out.mkdir();raw=root/'raw';raw.mkdir()
            session=Session([str(d.MAX_BILLABLE_BYTES).encode(),d.MAX_COST_USD.encode(),dbn_bytes(duplicate=True)])
            transport=DiagnosticHTTP(session=session,key='synthetic',temporary_root=raw)
            result=diagnose(transport,out)
            self.assertTrue(result['diagnostic_evidence_complete'])
            self.assertEqual(result['observation']['normalization_code'],'quote_order_not_strict')
            self.assertEqual(result['projection']['row_count'],2)
            self.assertEqual(len(session.calls),3)
            self.assertEqual(list(raw.iterdir()),[])
            self.assertFalse(result['runtime_input_eligible']);self.assertFalse(result['acquisition_gate_passed'])
            self.assertEqual([r['method'] for r in transport.attempts],['metadata.get_billable_size','metadata.get_cost','timeseries.get_range'])
            with self.assertRaises(q.MetadataFailure):transport.download()
            self.assertEqual(len(session.calls),3)

    @unittest.skipUnless(HAS_SDK,'pinned SDK covered by dedicated diagnostic validation')
    def test_actual_sdk_success_never_becomes_runtime_input(self):
        import databento
        observed,rows=d.inspect_store(databento.DBNStore.from_bytes(io.BytesIO(dbn_bytes())),d.request())
        self.assertEqual(observed['normalization_code'],'passed')
        self.assertEqual(rows[0]['fields']['ts_recv']['value'],d.request()['start_ns']+1)
        self.assertFalse(observed['runtime_input_eligible'])

    @unittest.skipUnless(HAS_SDK,'pinned SDK covered by dedicated diagnostic validation')
    def test_fresh_quote_increase_never_downloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);session=Session([str(d.MAX_BILLABLE_BYTES+1).encode(),d.MAX_COST_USD.encode()])
            transport=DiagnosticHTTP(session=session,key='synthetic',temporary_root=root)
            result=diagnose(transport,root)
            self.assertFalse(result['diagnostic_evidence_complete'])
            self.assertEqual(result['error'],'requote_unavailable_or_ceiling_exceeded')
            self.assertEqual(len(session.calls),2)

    @unittest.skipUnless(HAS_SDK,'pinned SDK covered by dedicated diagnostic validation')
    def test_overlarge_download_retains_failure_and_removes_partial_raw(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);session=Session([str(d.MAX_BILLABLE_BYTES).encode(),d.MAX_COST_USD.encode(),b'x'*(d.MAX_WIRE_BYTES+1)])
            transport=DiagnosticHTTP(session=session,key='synthetic',temporary_root=root)
            result=diagnose(transport,root)
            self.assertEqual(result['error'],'response_too_large')
            self.assertFalse((root/'diagnostic.dbn.zst').exists())
            self.assertEqual(transport.attempts[-1]['status'],'failed')
            self.assertEqual(len(session.calls),3)

    def test_execution_rejects_attempt_two_and_changed_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);workflow=root/d.WORKFLOW_PATH;workflow.parent.mkdir(parents=True)
            workflow.write_bytes((ROOT/d.WORKFLOW_PATH).read_bytes())
            execution=d.execution_payload(code_commit='a'*40,code_tree='b'*40,workflow_sha256=d.file_sha(workflow),ci_run_id='123',validation_run_id='124')
            d.write_json(root/d.EXECUTION_PATH,execution)
            env={'EXECUTION_CODE_COMMIT_SHA':'a'*40,'EXECUTION_CODE_TREE_SHA':'b'*40,'GITHUB_REPOSITORY':'RoomyRems/momentumbot','GITHUB_REF':'refs/heads/phase-3-historical-snapshot','GITHUB_EVENT_NAME':'push','GITHUB_RUN_ATTEMPT':'1','GITHUB_SHA':'c'*40,'GITHUB_RUN_ID':'125'}
            self.assertEqual(d.validate_execution(root,env),execution)
            for changed in ({'GITHUB_RUN_ATTEMPT':'2'},{'EXECUTION_CODE_TREE_SHA':'d'*40},{'GITHUB_REF':'refs/heads/main'}):
                with self.assertRaises(ValueError):d.validate_execution(root,{**env,**changed})

    def test_workflow_consumption_is_durable_before_only_provider_step(self):
        workflow=yaml.load((ROOT/d.WORKFLOW_PATH).read_text(),Loader=yaml.BaseLoader)
        self.assertEqual(set(workflow['on']),{'push'})
        steps=workflow['jobs']['diagnose']['steps']
        providers=[i for i,step in enumerate(steps) if 'DATABENTO_API_KEY' in step.get('env',{})]
        self.assertEqual(len(providers),1)
        for name in ('Verify the immutable failure artifact and parent refs','Durably upload consumption before provider access'):
            self.assertLess(next(i for i,s in enumerate(steps) if s.get('name')==name),providers[0])
        self.assertEqual(steps[-1]['if'],'always()')


if __name__=='__main__':unittest.main()
