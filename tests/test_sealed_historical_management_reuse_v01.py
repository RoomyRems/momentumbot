from __future__ import annotations

import copy
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
import warnings
import zipfile

import pandas as pd

from momentumbot.research import sealed_historical_management_reuse_v01 as m

ROOT = Path(__file__).resolve().parents[1]


def trade(stamp, identity=1, conditions=None):
    return {"t": pd.Timestamp(stamp).isoformat(), "p": 4.0, "s": 25,
            "x": "Q", "z": "C", "c": ["@"] if conditions is None else conditions, "i": identity}


def source_request():
    return {"request_id": "a" * 64, "symbol": "SYNTHETIC", "trading_date": "2025-05-30",
        "kind": "sip_trades", "feed": "sip", "asof": "2025-05-30", "adjustment": None,
        "start_inclusive": "2025-05-30T13:00:00+00:00", "end_exclusive": "2025-05-30T14:00:00+00:00"}


def fixture(path, requests, rows_by_id=None, change=None):
    members, receipts = {}, []
    for request in requests:
        stamp = pd.Timestamp(request["start_inclusive"]).isoformat()
        if request["kind"] == "sip_trades":
            rows = [trade(stamp)]
        else:
            rows = [{"t": stamp, "o": 4.0, "h": 4.0, "l": 4.0, "c": 4.0, "v": 25, "n": 1, "vw": 4.0}]
        rows = (rows_by_id or {}).get(request["request_id"], rows)
        raw = b"".join(m._canonical_line(row) for row in rows)
        compressed = gzip.compress(raw, mtime=0)
        relative = f"dates/{request['trading_date']}/{request['symbol']}-{request['kind']}.jsonl.gz"
        members[relative] = compressed
        receipt = {"request_id": request["request_id"], "path": relative, "record_count": len(rows),
            "logical_sha256": hashlib.sha256(raw).hexdigest(), "file_sha256": hashlib.sha256(compressed).hexdigest(),
            "retained_bytes": len(compressed), "pages": 1, "complete": True}
        receipts.append(receipt)
        members['receipts/' + request['request_id'] + '.json'] = m.accounts._bytes(m.seal(receipt))
    members["capture-report.json"] = m.accounts._bytes(m.seal({"status": "complete", "logical_requests_completed": len(requests), "receipts": receipts}))
    members["requests.json"] = m.accounts._bytes(m.seal({"requests": requests}))
    members["request-ledger.json"] = m.accounts._bytes({"total_attempts": len(requests), "blocked_attempts": 0})
    inventory = {"files": {name: hashlib.sha256(raw).hexdigest() for name, raw in members.items()},
                 "complete": True, "provider_attempts": len(requests), "blocked_attempts": 0}
    members["capture-inventory.json"] = m.accounts._bytes(m.seal(inventory))
    if change:
        change(members)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in members.items():
            archive.writestr(name, raw)
    return {"artifact_id": 1, "run_id": 2, "zip_sha256": m.file_sha(path), "file_count": len(members),
        "report_file_sha256": hashlib.sha256(members["capture-report.json"]).hexdigest(),
        "inventory_file_sha256": hashlib.sha256(members["capture-inventory.json"]).hexdigest(),
        "provider_attempts": len(requests), "record_count": sum(r["record_count"] for r in receipts),
        "prior_audit_content_sha256": "b" * 64}


class ManagementReuseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resources, cls.missing = m.derive_coverage(ROOT)

    def selector(self, lower=None, upper=None):
        start = pd.Timestamp('2025-05-30T13:30:00+00:00').value
        return {"coverage_id": "synthetic:sip", "source_request_id": "a" * 64,
                "covered_intervals": [[start if lower is None else lower, start + 2 if upper is None else upper]]}

    def verify(self, path, spec, requests=None, selectors=None):
        return m._verify_archive(path, spec, [source_request()] if requests is None else requests,
            [self.selector()] if selectors is None else selectors)

    def test_registration_preserves_account_seed_parent_and_all_closed_gates(self):
        value = m.validate_registration(ROOT)
        self.assertTrue(value['verification_passed'])
        self.assertEqual(m.contract(ROOT)['parent_commit_sha'], 'cf729c27d3e458e4762ee1d60d48a6c57a25a5d8')
        self.assertEqual(m.missing_contract(ROOT)['logical_request_count'], 10)
        self.assertFalse(m.missing_contract(ROOT)['provider_access_authorized_by_this_registration'])
        self.assertFalse(m.missing_contract(ROOT)['automatic_retries_allowed'])
        for key, expected in m.BOUNDARY.items():
            self.assertEqual(value[key], expected)

    def test_all_56_windows_and_109_opportunities_remain_with_51_full_envelopes(self):
        self.assertEqual(len(self.resources), 112)
        full = [r for r in self.resources if not r['missing_intervals']]
        self.assertEqual(len(full), 102)
        self.assertEqual(len({r['management_request_id'] for r in full}), 51)
        self.assertEqual(len({oid for r in self.resources for oid in r['opportunity_ids']}), 109)
        self.assertEqual(len(self.missing), 10)

    def test_missing_tails_are_exact_and_include_unavailable_jva(self):
        expected = {
            ('2025-06-09', 'TPST'): 946767019,
            ('2025-06-12', 'XTIA'): 660038644945,
            ('2025-06-13', 'JVA'): 689842083339,
            ('2025-07-02', 'LIXT'): 188881827631,
            ('2025-07-07', 'MBIO'): 86113575281,
        }
        for row in self.missing:
            self.assertEqual(row['start_ns'], pd.Timestamp(row['trading_date'] + 'T14:00:00Z').value)
            self.assertEqual(row['end_ns'] - row['start_ns'], expected[row['trading_date'], row['symbol']])
        self.assertEqual(sum(r['resource'] == 'sip_transactions' for r in self.missing), 5)
        self.assertEqual(sum(r['resource'] == 'raw_sip_1m_bars' for r in self.missing), 5)

    def test_interval_partition_unions_touching_and_overlapping_sources(self):
        self.assertEqual(m.partition_interval(10, 30, [(15, 20), (5, 12), (19, 25), (12, 15)]), ([[10, 25]], [[25, 30]]))
        self.assertEqual(m.partition_interval(10, 30, [(1, 5), (35, 40)]), ([], [[10, 30]]))
        self.assertEqual(m.partition_interval(10, 30, [(12, 15), (20, 25)]), ([[12, 15], [20, 25]], [[10, 12], [15, 20], [25, 30]]))

    def test_interval_partition_rejects_float_boolean_and_reversed_bounds(self):
        for args in ((True, 20, []), (10.0, 20, []), (20, 10, []), (10, 20, [(1, 1)]), (10, 20, [(1, False)])):
            with self.subTest(args=args), self.assertRaises(ValueError):
                m.partition_interval(*args)

    def test_partition_preserves_nanosecond_gaps(self):
        base = 1_748_613_600_000_000_000
        self.assertEqual(m.partition_interval(base, base + 100, [(base, base + 99)]), ([[base, base + 99]], [[base + 99, base + 100]]))

    def test_wire_urls_preserve_exact_bounds_raw_sip_identity_and_opaque_tokens(self):
        for row in (self.missing[0], self.missing[1]):
            u = urlsplit(m.missing_request_url(ROOT, row['request_id'], 'opaque&next=1'))
            q = parse_qs(u.query)
            self.assertEqual((u.scheme, u.netloc), ('https', 'data.alpaca.markets'))
            self.assertEqual(pd.Timestamp(q['start'][0]).value, row['start_ns'])
            self.assertEqual(pd.Timestamp(q['end'][0]).value, row['end_ns'] - 1)
            self.assertEqual(q['symbols'], [row['symbol']])
            self.assertEqual(q['asof'], [row['trading_date']])
            self.assertEqual(q['feed'], ['sip'])
            self.assertEqual(q['page_token'], ['opaque&next=1'])
            if row['kind'] == 'session_1m_raw':
                self.assertEqual(q['adjustment'], ['raw'])
                self.assertEqual(q['timeframe'], ['1Min'])
            else:
                self.assertNotIn('adjustment', q)

    def test_unregistered_request_or_invalid_pagination_fails(self):
        with self.assertRaisesRegex(ValueError, 'unregistered'):
            m.missing_request_url(ROOT, 'changed')
        for token in ('', True, 3):
            with self.subTest(token=token), self.assertRaises(ValueError):
                m.missing_request_url(ROOT, self.missing[0]['request_id'], token)

    def test_selected_rows_preserve_order_nanoseconds_and_unfiltered_conditions(self):
        start = self.selector()['covered_intervals'][0][0]
        rows = [trade(pd.Timestamp(t, unit='ns', tz='UTC'), i, conditions) for i, (t, conditions) in enumerate([
            (start - 1, ['@']), (start, ['I']), (start, ['?']), (start + 1, ['@']), (start + 2, ['@'])])]
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)/'source.zip'; spec = fixture(p, [source_request()], {'a'*64: rows})
            proof, picked = self.verify(p, spec)
        self.assertEqual(proof['record_count'], 5)
        item = picked[0]
        self.assertEqual(item['selected_record_count'], 3)
        self.assertEqual((item['first_source_record_ordinal'], item['last_source_record_ordinal']), (1, 3))
        expected = b''.join(str(i).encode()+b':'+m._canonical_line(rows[i]) for i in (1, 2, 3))
        self.assertEqual(item['selected_records_sha256'], hashlib.sha256(expected).hexdigest())
        self.assertFalse(item['management_trade_eligibility_filter_applied'])

    def test_no_observed_row_does_not_shrink_the_verified_request_envelope(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)/'source.zip'; spec = fixture(p, [source_request()])
            _, picked = self.verify(p, spec)
        self.assertEqual(picked[0]['selected_record_count'], 0)
        self.assertEqual(picked[0]['selected_records_sha256'], hashlib.sha256(b'').hexdigest())
        self.assertIsNone(picked[0]['first_source_record_ordinal'])
        covered, missing = m.partition_interval(20, 30, [(10, 40)])
        self.assertEqual((covered, missing), ([[20, 30]], []))

    def test_changed_archive_is_rejected_before_reading_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)/'source.zip'; spec = fixture(p, [source_request()])
            with p.open('ab') as h: h.write(b'changed')
            with self.assertRaisesRegex(ValueError, 'ZIP differs'):
                self.verify(p, spec)

    def test_unsafe_or_duplicate_archive_members_are_rejected(self):
        for name in ('../escape', '/absolute', 'a\\b', 'a/./b'):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w') as z:z.writestr(name, b'x')
            with zipfile.ZipFile(stream) as z, self.subTest(name=name), self.assertRaisesRegex(ValueError, 'unsafe'):
                m._safe_members(z, 1)
        stream = io.BytesIO()
        with warnings.catch_warnings(), zipfile.ZipFile(stream, 'w') as z:
            warnings.simplefilter('ignore'); z.writestr('same', b'a'); z.writestr('same', b'b')
        with zipfile.ZipFile(stream) as z, self.assertRaisesRegex(ValueError, 'population'):
            m._safe_members(z, 2)

    def test_each_retained_file_hash_is_checked(self):
        def change(members): members['request-ledger.json'] += b' '
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'source.zip'; spec=fixture(p,[source_request()],change=change)
            with self.assertRaisesRegex(ValueError, 'all source member bytes'):
                self.verify(p,spec)

    def test_wrong_request_identity_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'source.zip';spec=fixture(p,[source_request()])
            changed={**source_request(),'symbol':'OTHER'}
            with self.assertRaisesRegex(ValueError, 'original source requests'):
                self.verify(p,spec,[changed])

    def test_incomplete_ledger_is_rejected_even_with_rehashed_inventory(self):
        def change(members):
            members['request-ledger.json']=m.accounts._bytes({'total_attempts':1,'blocked_attempts':1})
            inv=json.loads(members['capture-inventory.json']);inv.pop('content_sha256')
            inv['files']['request-ledger.json']=hashlib.sha256(members['request-ledger.json']).hexdigest()
            members['capture-inventory.json']=m.accounts._bytes(m.seal(inv))
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'source.zip';spec=fixture(p,[source_request()],change=change)
            with self.assertRaisesRegex(ValueError, 'completeness or ledger'):
                self.verify(p,spec)

    def test_required_selected_fields_are_normalized_fail_closed(self):
        start=self.selector()['covered_intervals'][0][0]
        for key,value in (('p',-1.0),('s',1.5),('x',''),('c',None),('z','X')):
            row=trade(pd.Timestamp(start,unit='ns',tz='UTC'));row[key]=value
            with self.subTest(key=key),tempfile.TemporaryDirectory() as temp:
                p=Path(temp)/'source.zip';spec=fixture(p,[source_request()],{'a'*64:[row]})
                with self.assertRaises(m.sip.CaptureError):self.verify(p,spec)

    def test_noncanonical_selected_row_cannot_be_silently_repaired(self):
        start=self.selector()['covered_intervals'][0][0]
        row=trade(pd.Timestamp(start,unit='ns',tz='UTC'));row['extra']='must not be dropped'
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'source.zip';spec=fixture(p,[source_request()],{'a'*64:[row]})
            with self.assertRaisesRegex(ValueError,'normalization changed'):self.verify(p,spec)

    def test_source_order_is_not_silently_sorted(self):
        start=self.selector()['covered_intervals'][0][0]
        rows=[trade(pd.Timestamp(start+delta,unit='ns',tz='UTC'),i) for i,delta in enumerate((1,0))]
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'source.zip';spec=fixture(p,[source_request()],{'a'*64:rows})
            with self.assertRaisesRegex(ValueError,'order differs'):self.verify(p,spec)

    def test_full_tape_logical_hash_is_checked_even_without_selected_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'source.zip';fixture(p,[source_request()])
            with zipfile.ZipFile(p) as z:
                receipt=m._sealed(z.read('receipts/'+'a'*64+'.json'))
                receipt['logical_sha256']='0'*64
                with self.assertRaisesRegex(ValueError,'logical tape'):
                    m._scan_tape(z,source_request(),receipt,[])

    def test_source_normalization_preserves_management_bar_and_trade_projection_inputs(self):
        from momentumbot.providers.alpaca_trades import trade_frame
        from momentumbot.research.prospective_management_window import _frame_trade_rows, _frame_bar_rows
        req=source_request();start=pd.Timestamp(req['start_inclusive']).value
        raw=[trade(req['start_inclusive'],1,['I']),trade(req['start_inclusive'],2,['?']),trade(req['start_inclusive'],3,['@'])]
        normalized=[m.sip.normalized_row(row,req) for row in raw]
        bounds={'start_ns':start,'end_ns':start+60_000_000_000}
        self.assertEqual(_frame_trade_rows(trade_frame(raw),bounds),_frame_trade_rows(trade_frame(normalized),bounds))
        bar_req={**req,'kind':'session_1m_raw','adjustment':'raw'}
        bar={'t':req['start_inclusive'],'o':4.0,'h':5.0,'l':3.0,'c':3.5,'v':100,'n':5,'vw':4.0}
        row=m.sip.normalized_row(bar,bar_req)
        frame=pd.DataFrame({'open':[row['o']],'close':[row['c']]},index=pd.DatetimeIndex([row['t']]))
        self.assertEqual(_frame_bar_rows(frame,bounds),[{'timestamp_ns':start,'open':4.0,'close':3.5}])

    def test_synthetic_full_population_roundtrip_write_once_and_tamper_detection(self):
        requests=m.source_requests(ROOT)
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);sip_zip=base/'sip.zip';bars_zip=base/'bars.zip'
            specs={'sip_transactions':fixture(sip_zip,requests['sip_transactions']),
                   'raw_sip_1m_bars':fixture(bars_zip,requests['raw_sip_1m_bars'])}
            output=base/'output'
            with patch.object(m,'source_spec',side_effect=lambda root,key:specs[key]):
                built=m.write_bundle(ROOT,output,sip_zip=sip_zip,bars_zip=bars_zip)
                checked=m.verify_bundle(ROOT,output,sip_zip=sip_zip,bars_zip=bars_zip)
                self.assertEqual(built,checked)
                self.assertEqual(checked['readiness']['missing_logical_request_count'],10)
                self.assertEqual(len(checked['readiness']['unavailable_entry_opportunities']),23)
                self.assertFalse(checked['readiness']['all_management_sources_complete'])
                with self.assertRaises(FileExistsError):m.write_bundle(ROOT,output,sip_zip=sip_zip,bars_zip=bars_zip)
                path=output/'reuse-coverage.json';value=m.frozen(path);value.pop('content_sha256')
                value['resources'][0]['selection_evidence']['selected_record_count']+=1
                path.write_bytes(m.accounts._bytes(m.seal(value)))
                with self.assertRaisesRegex(ValueError,'source reconstruction'):
                    m.verify_bundle(ROOT,output,sip_zip=sip_zip,bars_zip=bars_zip)

    def test_output_cannot_overwrite_parent_or_follow_symlink(self):
        with self.assertRaisesRegex(ValueError,'cannot overwrite'):
            m._output(ROOT,ROOT/m.accounts.OUTPUT_PATH)
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);(p/'link').symlink_to(p/'target')
            with self.assertRaisesRegex(ValueError,'symlink'):m._output(ROOT,p/'link')

    def test_cli_registration_succeeds_under_offline_audit_guard(self):
        env={**os.environ,'PYTHONPATH':str(ROOT/'src')+':'+str(ROOT/'scripts'),'PYTHONDONTWRITEBYTECODE':'1'}
        result=subprocess.run([sys.executable,str(ROOT/m.SCRIPT_PATH),'--validate-registration'],env=env,cwd=ROOT,text=True,capture_output=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['provider_calls'],0)


if __name__ == '__main__':
    unittest.main()
