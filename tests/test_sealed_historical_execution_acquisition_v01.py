from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import gzip
import pandas as pd
import yaml

from momentumbot.research import sealed_historical_execution_acquisition_v01 as acq
from momentumbot.research import sealed_historical_execution_quote_v01 as quote
from momentumbot.research.sealed_historical_execution_transport_v01 import ExactTimeseriesHTTP,sdk_timeseries

ROOT=Path(__file__).resolve().parents[1]
HAS_SDK=importlib.util.find_spec('databento') is not None


class Store:
    def __init__(self,request,bad=False):
        self.request=request;self.bad=bad
        self.metadata={k:request[k] for k in ('dataset','schema','symbols','stype_in')}
        self.metadata.update(start=request['start_ns'],end=request['end_ns'])

    def to_df(self,**kwargs):
        r=self.request
        base={'symbol':'OTHER' if self.bad else r['symbols'][0],'ts_recv':r['start_ns']+1}
        if r['schema']=='mbp-1':base.update(sequence=1,bid_px_00=1_000_000_000,bid_sz_00=10,ask_px_00=1_010_000_000,ask_sz_00=20)
        else:base.update(action=1,is_trading='Y')
        return pd.DataFrame([base])


class Client:
    def __init__(self,requests,fail=None):self.requests=requests;self.calls=[];self.fail=fail
    def get_range(self,path,**kwargs):
        i=len(self.calls);self.calls.append(kwargs)
        Path(path).write_bytes(b'synthetic-ephemeral-dbn')
        if i==self.fail:raise RuntimeError('synthetic-secret must not persist')
        return Store(self.requests[i])


class Response:
    def __init__(self,body=b'synthetic-dbn',status=200):self.body=body;self.status_code=status
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def iter_content(self,size):yield self.body


class Session:
    def __init__(self,status=200,body=b'synthetic-dbn'):self.calls=[];self.status=status;self.body=body
    def post(self,url,**kwargs):
        self.calls.append((url,kwargs));return Response(self.body,self.status)


class HistoricalExecutionAcquisitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.requests,cls.parent=acq.validate_inputs(ROOT)
        cls.preflight=acq.preflight(cls.requests,deepcopy(cls.parent['calls']),provenance={'test':'synthetic'},http_attempts=180,blocked_attempts=0)

    def test_exact_registration_quote_and_ceilings(self):
        self.assertEqual(len(self.requests),90)
        self.assertEqual(acq.contract()['maximum_quoted_cost_usd'],'0.172787457709')
        self.assertEqual(acq.contract()['maximum_billable_bytes'],154456640)
        self.assertTrue(self.preflight['preflight_passed'])

    def test_requote_cost_or_size_increase_blocks_before_any_download(self):
        for index,amount in ((0,1),(1,'0.2')):
            calls=deepcopy(self.parent['calls'])
            calls[index]['value'] = calls[index]['value'] + amount if index==0 else amount
            result=acq.preflight(self.requests,calls,provenance={},http_attempts=180,blocked_attempts=0)
            self.assertFalse(result['preflight_passed'])
            client=Client(self.requests)
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(ValueError):acq.acquire_tapes(self.requests,result,client=client,output=Path(tmp),temporary_root=Path(tmp))
            self.assertEqual(client.calls,[])

    def test_zero_size_blocks_all_downloads_without_substitution(self):
        calls=deepcopy(self.parent['calls']);calls[0]['value']=0
        result=acq.preflight(self.requests,calls,provenance={},http_attempts=180,blocked_attempts=0)
        self.assertFalse(result['preflight_passed'])
        self.assertEqual(len(result['metadata_result']['quote_rows']),90)

    def test_complete_exact_tapes_are_deterministic_and_raw_files_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);raw=root/'raw';raw.mkdir();out=root/'out'
            client=Client(self.requests)
            rows=acq.acquire_tapes(self.requests,self.preflight,client=client,output=out,temporary_root=raw)
            self.assertEqual(len(rows),90);self.assertTrue(all(r['status']=='complete' for r in rows))
            self.assertEqual(list(raw.iterdir()),[])
            self.assertEqual(len(list((out/'tapes').iterdir())),90)
            self.assertEqual(len(list((out/'receipts').iterdir())),90)
            content=gzip.decompress((out/rows[0]['tape']['path']).read_bytes())
            self.assertEqual(json.loads(content)['symbol'],self.requests[0]['symbols'][0])
            first=out/rows[0]['tape']['path'];second=root/'again.gz'
            result=acq.write_tape(second,[json.loads(content)])
            self.assertEqual(acq.file_sha(first),result['file_sha256'])
            self.assertEqual(client.calls[0],quote.request_kwargs(self.requests[0]))

    def test_first_failure_stops_later_downloads_retains_completed_tapes_and_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);raw=root/'raw';raw.mkdir();out=root/'out';states=[]
            client=Client(self.requests,fail=2)
            rows=acq.acquire_tapes(self.requests,self.preflight,client=client,output=out,temporary_root=raw,progress=lambda x:states.append(deepcopy(x)))
            self.assertEqual(len(client.calls),3)
            self.assertEqual([r['status'] for r in rows],['complete','complete','failed'])
            self.assertEqual(rows[-1]['failure_stage'],'timeseries_request')
            self.assertEqual(len(list((out/'tapes').iterdir())),2)
            self.assertEqual(list(raw.iterdir()),[])
            self.assertNotIn('synthetic-secret',json.dumps(rows))
            self.assertFalse(states[-1]['complete'])
            self.assertEqual(states[0]['requests'][0]['status'],'pending')

    def test_wrong_symbol_bound_or_record_order_rejected(self):
        request=self.requests[0]
        with self.assertRaises(ValueError):acq.normalize(Store(request,bad=True),request)
        store=Store(request);store.metadata['end']+=1
        with self.assertRaises(ValueError):acq.normalize(store,request)
        with patch.object(Store,'to_df',return_value=pd.concat([Store(request).to_df(),Store(request).to_df()])):
            with self.assertRaises(ValueError):acq.normalize(Store(request),request)

    def test_rehashed_report_bytes_cannot_replace_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/acq.QUOTE_REPORT_PATH;path.parent.mkdir(parents=True)
            value=deepcopy(self.parent);value.pop('content_sha256');value['total_quoted_cost_usd']='0'
            acq.write_json(path,acq.seal(value))
            with self.assertRaises(ValueError):acq.quote_parent(root)

    def test_execution_binds_new_consumption_and_rejects_attempt_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/acq.WORKFLOW_PATH;path.parent.mkdir(parents=True);path.write_bytes((ROOT/acq.WORKFLOW_PATH).read_bytes())
            payload=acq.execution_payload(code_commit='a'*40,code_tree='b'*40,workflow_sha256=acq.file_sha(path),ci_run_id='12345',validation_run_id='12346')
            acq.write_json(root/acq.EXECUTION_PATH,payload)
            env={'EXECUTION_CODE_COMMIT_SHA':'a'*40,'EXECUTION_CODE_TREE_SHA':'b'*40,'GITHUB_REPOSITORY':'RoomyRems/momentumbot','GITHUB_EVENT_NAME':'push','GITHUB_REF':'refs/heads/phase-3-historical-snapshot','GITHUB_RUN_ATTEMPT':'1','GITHUB_SHA':'c'*40,'GITHUB_RUN_ID':'12347'}
            self.assertEqual(acq.validate_execution(root,env),payload)
            self.assertNotEqual(payload['consumption_ref'],quote.CONSUMPTION_REF)
            with self.assertRaises(ValueError):acq.validate_execution(root,{**env,'GITHUB_RUN_ATTEMPT':'2'})

    @unittest.skipUnless(HAS_SDK,'actual pinned SDK covered in dedicated acquisition validation')
    def test_real_dbn_roundtrip_preserves_exact_nanos_fixed_prices_and_status(self):
        from datetime import date,timedelta
        from types import SimpleNamespace as N
        import io
        import databento as db,databento_dbn as d
        for schema in ('mbp-1','status'):
            with self.subTest(schema=schema):
                r=next(x for x in self.requests if x['schema']==schema)
                ns=r['start_ns']+1;day=date.fromisoformat(r['trading_date'])
                meta=d.Metadata(dataset='XNAS.ITCH',start=r['start_ns'],end=r['end_ns'],
                    stype_in=d.SType.RAW_SYMBOL,stype_out=d.SType.INSTRUMENT_ID,schema=d.Schema(schema),
                    symbols=r['symbols'],mappings=[N(raw_symbol=r['symbols'][0],intervals=[N(start_date=day,end_date=day+timedelta(days=1),symbol='1')])])
                if schema=='mbp-1':
                    msg=d.MBP1Msg(publisher_id=2,instrument_id=1,ts_event=ns-1,price=1000000000,size=10,
                        action=d.Action.ADD,side=d.Side.BID,depth=0,ts_recv=ns,sequence=1,
                        levels=d.BidAskPair(bid_px=1000000000,ask_px=1010000000,bid_sz=10,ask_sz=20))
                else:
                    msg=d.StatusMsg(publisher_id=2,instrument_id=1,ts_event=ns-1,ts_recv=ns,
                        action=d.StatusAction.TRADING,is_trading=d.TriState.YES)
                store=db.DBNStore.from_bytes(io.BytesIO(meta.encode()+bytes(msg)))
                rows=acq.normalize(store,r)
                self.assertEqual(len(rows),1)
                self.assertEqual(rows[0]['ts_recv_ns'],ns)
                self.assertEqual(rows[0]['symbol'],r['symbols'][0])
                if schema=='mbp-1':
                    self.assertEqual((rows[0]['bid_px_nanos'],rows[0]['ask_px_nanos']),(1000000000,1010000000))
                else:
                    self.assertEqual((rows[0]['action'],rows[0]['is_trading']),(7,'Y'))

    @unittest.skipUnless(HAS_SDK,'actual pinned SDK covered in dedicated acquisition validation')
    def test_real_sdk_exact_request_and_no_redirect_retry_or_broader_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);session=Session()
            transport=ExactTimeseriesHTTP(self.requests,self.parent,self.preflight,session=session,key='synthetic',temporary_root=root,pause=lambda _:None)
            with patch('databento.DBNStore.from_file',return_value=Store(self.requests[0])):
                sdk_timeseries(transport).get_range(path=str(root/'request-000.dbn.zst'),**quote.request_kwargs(self.requests[0]))
            self.assertEqual(len(session.calls),1)
            self.assertFalse(session.calls[0][1]['allow_redirects'])
            with self.assertRaises(quote.MetadataFailure):
                transport.stream('https://hist.databento.com/v0/batch.submit_job',{},True,root/'request-001.dbn.zst')
            self.assertEqual(len(session.calls),1)

    @unittest.skipUnless(HAS_SDK,'actual pinned SDK covered in dedicated acquisition validation')
    def test_http_error_or_wire_ceiling_is_one_attempt(self):
        for session in (Session(status=302),Session(body=b'x'*(self.parent['quote_rows'][0]['billable_size_bytes']+65537))):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);transport=ExactTimeseriesHTTP(self.requests,self.parent,self.preflight,session=session,key='synthetic',temporary_root=root,pause=lambda _:None)
                with self.assertRaises(quote.MetadataFailure):sdk_timeseries(transport).get_range(path=str(root/'request-000.dbn.zst'),**quote.request_kwargs(self.requests[0]))
                self.assertEqual(len(session.calls),1);self.assertEqual(transport.attempts[0]['status'],'failed')

    def test_workflow_parent_quote_and_durable_consumption_before_secret(self):
        workflow=yaml.load((ROOT/acq.WORKFLOW_PATH).read_text(),Loader=yaml.BaseLoader)
        self.assertEqual(set(workflow['on']),{'push'})
        steps=workflow['jobs']['acquire']['steps']
        provider=next(i for i,s in enumerate(steps) if 'DATABENTO_API_KEY' in s.get('env',{}))
        for name in ('Download and verify the exact independently verified parent quote','Durably upload consumption before provider access'):
            self.assertLess(next(i for i,s in enumerate(steps) if s.get('name')==name),provider)
        self.assertEqual(steps[-1]['if'],'always()')


if __name__=='__main__':unittest.main()
