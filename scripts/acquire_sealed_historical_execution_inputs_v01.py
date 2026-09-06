"""Validate or consume one exact quote-bound historical input acquisition."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from run_offline_python_v13 import deny_external_io
from momentumbot.research import sealed_historical_execution_acquisition_v01 as acq
from momentumbot.research import sealed_historical_execution_quote_v01 as quote
from momentumbot.research.sealed_historical_metadata_transport_v01 import MetadataOnlyHTTP, sdk_metadata
from momentumbot.research.sealed_historical_execution_transport_v01 import ExactTimeseriesHTTP, sdk_timeseries

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--validate-only',action='store_true')
    modes.add_argument('--consume',action='store_true')
    modes.add_argument('--acquire',action='store_true')
    parser.add_argument('--check-execution',action='store_true')
    parser.add_argument('--preflight-root',type=Path)
    parser.add_argument('--output-root',type=Path)
    args = parser.parse_args()
    if not args.acquire: sys.addaudithook(deny_external_io)
    requests, parent = acq.validate_inputs(ROOT)
    if args.check_execution or args.consume or args.acquire:
        execution = acq.validate_execution(ROOT,os.environ)
    if args.validate_only:
        print(json.dumps({'valid':True,'requests':90,'maximum_billable_bytes':acq.MAX_BILLABLE_BYTES,'maximum_quoted_cost_usd':acq.MAX_COST_USD,'provider_calls':0})); return 0
    pre = args.preflight_root
    if pre is None: parser.error('preflight root required')
    acq.verify_quote_zip(pre / 'parent-quote.zip',ROOT)
    expected = acq.consumption(execution,os.environ)
    if args.consume:
        ref = json.loads((pre / 'consumption-ref.json').read_text())
        if ref.get('ref') != acq.CONSUMPTION_REF or ref.get('object',{}).get('sha') != os.environ['GITHUB_SHA']:
            raise ValueError('durable exact consumption ref required')
        acq.write_json(pre / 'consumption.json',expected)
        for path,name in ((ROOT / acq.EXECUTION_PATH,'execution.json'),(ROOT / acq.CONTRACT_PATH,'contract.json'),(ROOT / quote.LOCK_PATH,quote.LOCK_PATH)):
            shutil.copyfile(path,pre / name)
        return 0
    marker = acq.frozen(pre / 'consumption.json')
    quote.require_exact(marker,expected,'durable acquisition consumption')
    output = args.output_root
    if output is None: parser.error('output root required')
    if output.exists() or output.is_symlink(): raise ValueError('new write-once capture directory required')
    output.mkdir(parents=True)
    for path,name in ((pre / 'consumption.json','consumption.json'),(ROOT / acq.EXECUTION_PATH,'execution.json'),
        (ROOT / acq.CONTRACT_PATH,'contract.json'),(ROOT / quote.PLAN_PATH / 'request-manifest.json','request-manifest.json'),
        (ROOT / acq.QUOTE_REPORT_PATH,'parent-quote-report.json')):
        shutil.copyfile(path,output / name)
    provenance = {'execution_commit_sha':os.environ['GITHUB_SHA'],'workflow_run_id':os.environ['GITHUB_RUN_ID'],
        'workflow_run_attempt':1,'code_commit_sha':execution['code_commit_sha'],'code_tree_sha':execution['code_tree_sha'],
        'execution_content_sha256':execution['content_sha256'],'consumption_content_sha256':marker['content_sha256']}
    report = {'contract_id':acq.CONTRACT_ID,'artifact_type':'historical_execution_input_acquisition_report','provenance':provenance,
        'parent_quote_report_content_sha256':acq.QUOTE_REPORT_CONTENT_SHA,'requests':[],'requote':None,
        'error':None,'http_attempts':0,'metadata_http_attempts':0,'timeseries_http_attempts':0,'blocked_attempts':0,
        'request_count':90,'date_count':30,'opportunity_count':109,'symbol_date_count':45,
        'raw_dbn_retained':False,'raw_temp_directory_removed':True,'account_or_fill_simulation_executed':False,
        'backtesting_executed':False,'retrospective_inputs_loaded':False,'policy_changed':False,
        'automatic_retry_attempted':False,'quote_or_prior_acquisition_rerun':False,'actual_billing_known':False,
        'acquisition_gate_passed':False,'next_gate':'independent_input_verification_then_historical_capture_composition'}
    key = os.environ.get('DATABENTO_API_KEY','')
    session = metadata_transport = timeseries_transport = None
    try:
        if not key: raise ValueError('credential_missing')
        import databento
        import requests as http
        if databento.__version__ != quote.SDK_VERSION: raise ValueError('sdk_version_mismatch')
        session = http.Session(); session.trust_env = False
        metadata_transport = MetadataOnlyHTTP(requests,session=session,key=key,
            progress=lambda value:acq.write_json(output / 'metadata-http-ledger.json',value,replace=True))
        calls = quote.collect_quote(requests,sdk_metadata(metadata_transport),
            progress=lambda value:acq.write_json(output / 'metadata-ledger.json',value,replace=True))
        requote = acq.preflight(requests,calls,provenance=provenance,http_attempts=len(metadata_transport.attempts),blocked_attempts=metadata_transport.blocked)
        report['requote'] = requote
        acq.write_json(output / 'requote-report.json',requote)
        if not requote['preflight_passed']:
            report['error'] = 'requote_unavailable_or_ceiling_exceeded'
        else:
            with tempfile.TemporaryDirectory(prefix='historical-execution-input-') as tmp:
                temporary_root = Path(tmp)
                timeseries_transport = ExactTimeseriesHTTP(requests,parent,requote,session=session,key=key,temporary_root=temporary_root,
                    progress=lambda value:acq.write_json(output / 'timeseries-http-ledger.json',value,replace=True))
                rows = acq.acquire_tapes(requests,requote,client=sdk_timeseries(timeseries_transport),output=output,temporary_root=temporary_root,
                    progress=lambda value:acq.write_json(output / 'download-ledger.json',value,replace=True))
                report['requests'] = rows
                report['raw_dbn_retained'] = any(temporary_root.iterdir())
            report['raw_temp_directory_removed'] = not temporary_root.exists()
            if len(rows) == 90 and all(r['status'] == 'complete' for r in rows) and not report['raw_dbn_retained']:
                report['acquisition_gate_passed'] = True
            else:
                report['error'] = 'download_or_normalization_incomplete'
    except Exception:
        report['error'] = 'credential_missing' if not key else 'acquisition_preflight_or_runtime_failed'
    finally:
        if session is not None: session.close()
        if metadata_transport:
            metadata_transport.save()
            report['metadata_http_attempts'] = len(metadata_transport.attempts)
            report['blocked_attempts'] += metadata_transport.blocked
        if timeseries_transport:
            timeseries_transport.save()
            report['timeseries_http_attempts'] = len(timeseries_transport.attempts)
            report['blocked_attempts'] += timeseries_transport.blocked
        report['http_attempts'] = report['metadata_http_attempts'] + report['timeseries_http_attempts']
        if report['blocked_attempts'] or report['error']: report['acquisition_gate_passed'] = False
        report['completed_request_count'] = sum(r['status']=='complete' for r in report['requests'])
        report['normalized_row_count'] = sum(r['tape']['row_count'] for r in report['requests'] if r['status']=='complete')
        report = acq.seal(report)
        if key and key in json.dumps(report,sort_keys=True): raise ValueError('sanitized serialization rejected')
        acq.write_json(output / 'capture-report.json',report)
        files = {p.relative_to(output).as_posix():{'sha256':acq.file_sha(p),'bytes':p.stat().st_size} for p in sorted(output.rglob('*')) if p.is_file()}
        acq.write_json(output / 'capture-inventory.json',acq.seal({'contract_id':acq.CONTRACT_ID,'provenance':provenance,'files':files,'acquisition_gate_passed':report['acquisition_gate_passed']}))
    print(json.dumps({k:report[k] for k in ('acquisition_gate_passed','completed_request_count','normalized_row_count','http_attempts','blocked_attempts','error')}))
    return 0 if report['acquisition_gate_passed'] else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        print('{"status":"failed","sanitized_error":"historical acquisition validation failed"}',file=sys.stderr)
        raise SystemExit(1) from None
