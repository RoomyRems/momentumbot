"""Consume a separate, bounded diagnostic of the exact first GITS request."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import tempfile

from run_offline_python_v13 import deny_external_io
from momentumbot.research import sealed_historical_execution_diagnostic_v01 as diag
from momentumbot.research import sealed_historical_execution_quote_v01 as quote
from momentumbot.research.sealed_historical_execution_diagnostic_transport_v01 import DiagnosticHTTP

ROOT = Path(__file__).resolve().parents[1]


def diagnose(transport, output: Path) -> dict:
    """Retain the bounded projection and diagnostic even when normalization fails."""
    raw = transport.root / 'diagnostic.dbn.zst'
    projection = output / 'diagnostic-projection.jsonl.gz'
    result = {'requote':None,'observation':None,'projection':None,'error':None,
        'ephemeral_dbn_sha256':None,'same_dbn_bytes_as_failed_parent':False,
        'raw_dbn_retained':False,'diagnostic_evidence_complete':False,
        'runtime_input_eligible':False,'acquisition_gate_passed':False}
    store = None
    try:
        requote = transport.requote()
        result['requote'] = requote
        diag.write_json(output/'requote-report.json',requote)
        if not requote['preflight_passed']:
            result['error'] = 'requote_unavailable_or_ceiling_exceeded'
            return result
        store = transport.download()
        if not raw.is_file() or not 0 < raw.stat().st_size <= diag.MAX_WIRE_BYTES:
            raise ValueError('missing_or_oversized_dbn')
        result['ephemeral_dbn_sha256'] = diag.file_sha(raw)
        result['same_dbn_bytes_as_failed_parent'] = result['ephemeral_dbn_sha256']==diag.PRIOR_DBN_SHA
        observation, rows = diag.inspect_store(store,diag.request())
        result['observation'] = observation
        diag.write_json(output/'normalization-observation.json',observation)
        result['projection'] = diag.write_projection(projection,rows)
        diag.write_json(output/'diagnostic-receipt.json',diag.seal({
            'request':diag.request(),'request_content_sha256':diag.REQUEST_SHA,
            'ephemeral_dbn_sha256':result['ephemeral_dbn_sha256'],
            'observation_content_sha256':observation['content_sha256'],
            'projection':result['projection'],'runtime_input_eligible':False}))
        result['diagnostic_evidence_complete'] = observation['frame'].get('mapping_passed') is True
        if not result['diagnostic_evidence_complete']:
            result['error'] = 'mapped_projection_unavailable'
    except quote.MetadataFailure as exc:
        result['error'] = exc.code
    except Exception:
        result['error'] = 'diagnostic_runtime_or_retention_failed'
        if result['projection'] is None:
            projection.unlink(missing_ok=True)
    finally:
        if store is not None:
            reader = getattr(store,'reader',None)
            if reader is not None:
                reader.close()
        raw.unlink(missing_ok=True)
        result['raw_dbn_retained'] = raw.exists()
        if result['error'] or transport.blocked or result['raw_dbn_retained']:
            result['diagnostic_evidence_complete'] = False
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--validate-only',action='store_true')
    modes.add_argument('--consume',action='store_true')
    modes.add_argument('--diagnose',action='store_true')
    parser.add_argument('--check-execution',action='store_true')
    parser.add_argument('--preflight-root',type=Path)
    parser.add_argument('--output-root',type=Path)
    args = parser.parse_args()
    if not args.diagnose:
        sys.addaudithook(deny_external_io)
    diag.validate_inputs(ROOT)
    if args.check_execution or args.consume or args.diagnose:
        execution = diag.validate_execution(ROOT,os.environ)
        if platform.python_implementation()!='CPython' or platform.python_version()!='3.12.14':
            raise ValueError('exact hosted CPython required')
    if args.validate_only:
        print(json.dumps({'valid':True,'request_count':1,'maximum_http_attempts':3,'provider_calls':0})); return 0
    pre = args.preflight_root
    if pre is None:
        parser.error('preflight root required')
    diag.verify_failure_zip(pre/'parent-failure.zip',ROOT)
    expected = diag.consumption(execution,os.environ)
    if args.consume:
        ref = json.loads((pre/'consumption-ref.json').read_text())
        if ref.get('ref')!=diag.CONSUMPTION_REF or ref.get('object',{}).get('sha')!=os.environ['GITHUB_SHA']:
            raise ValueError('exact durable diagnostic ref required')
        diag.write_json(pre/'consumption.json',expected)
        for path, name in ((diag.CONTRACT_PATH,'contract.json'),(diag.EXECUTION_PATH,'execution.json'),(quote.LOCK_PATH,quote.LOCK_PATH)):
            shutil.copyfile(ROOT/path,pre/name)
        return 0
    marker = diag.frozen(pre/'consumption.json')
    quote.require_exact(marker,expected,'diagnostic consumption')
    output = args.output_root
    if output is None:
        parser.error('output root required')
    if output.exists() or output.is_symlink():
        raise ValueError('new write-once diagnostic output required')
    output.mkdir(parents=True)
    for path, name in ((diag.CONTRACT_PATH,'contract.json'),(diag.EXECUTION_PATH,'execution.json'),
        (diag.FAILURE_AUDIT_PATH,'parent-failure-audit.json'),(diag.FAILURE_REPORT_PATH,'parent-failure-report.json'),
        (diag.parent.QUOTE_REPORT_PATH,'parent-quote-report.json')):
        shutil.copyfile(ROOT/path,output/name)
    shutil.copyfile(pre/'consumption.json',output/'consumption.json')
    diag.write_json(output/'request.json',diag.seal({'request':diag.request(),'request_content_sha256':diag.REQUEST_SHA}))
    provenance = {'execution_commit_sha':os.environ['GITHUB_SHA'],'workflow_run_id':os.environ['GITHUB_RUN_ID'],
        'workflow_run_attempt':1,'code_commit_sha':execution['code_commit_sha'],'code_tree_sha':execution['code_tree_sha'],
        'execution_content_sha256':execution['content_sha256'],'consumption_content_sha256':marker['content_sha256']}
    report = {'contract_id':diag.CONTRACT_ID,'artifact_type':'historical_execution_input_normalization_diagnostic',
        'contract_content_sha256':diag.contract()['content_sha256'],'provenance':provenance,
        'failure_zip_sha256':diag.FAILURE_ZIP_SHA,'request_content_sha256':diag.REQUEST_SHA,
        'diagnostic_evidence_complete':False,'error':None,'runtime_input_eligible':False,'acquisition_gate_passed':False,
        'account_or_fill_simulation_executed':False,'backtesting_executed':False,'retrospective_inputs_loaded':False,
        'policy_changed':False,'consumed_parent_rerun':False,'actual_billing_known':False,
        'raw_temp_directory_removed':True,'raw_dbn_retained':False,'http_attempts':0,'blocked_attempts':0,
        'next_gate':diag.contract()['next_gate']}
    session = transport = None
    key = os.environ.get('DATABENTO_API_KEY','')
    try:
        if not key:
            raise ValueError('credential_missing')
        import databento
        import requests
        if databento.__version__!=quote.SDK_VERSION:
            raise ValueError('sdk_version_mismatch')
        session = requests.Session(); session.trust_env = False
        with tempfile.TemporaryDirectory(prefix='execution-diagnostic-') as tmp:
            transport = DiagnosticHTTP(session=session,key=key,temporary_root=Path(tmp),
                progress=lambda value:diag.write_json(output/'http-ledger.json',value,replace=True))
            report.update(diagnose(transport,output))
        report['raw_temp_directory_removed'] = not Path(tmp).exists()
    except Exception:
        report['error'] = 'diagnostic_preflight_or_runtime_failed' if key else 'credential_missing'
    finally:
        if session is not None:
            session.close()
        if transport is not None:
            transport.save()
            report.update(http_attempts=len(transport.attempts),blocked_attempts=transport.blocked)
        if report['error'] or report['blocked_attempts'] or not report['raw_temp_directory_removed']:
            report['diagnostic_evidence_complete'] = False
        report = diag.seal(report)
        if key and key in json.dumps(report,sort_keys=True):
            raise ValueError('sanitized serialization rejected')
        diag.write_json(output/'diagnostic-report.json',report)
        files = {p.relative_to(output).as_posix():{'sha256':diag.file_sha(p),'bytes':p.stat().st_size}
                 for p in sorted(output.rglob('*')) if p.is_file()}
        diag.write_json(output/'diagnostic-inventory.json',diag.seal({'contract_id':diag.CONTRACT_ID,
            'provenance':provenance,'files':files,'runtime_input_eligible':False,
            'diagnostic_evidence_complete':report['diagnostic_evidence_complete']}))
    print(json.dumps({k:report[k] for k in ('diagnostic_evidence_complete','http_attempts','blocked_attempts','error')}))
    return 0 if report['diagnostic_evidence_complete'] else 1


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except Exception:
        print('{"status":"failed","sanitized_error":"diagnostic validation failed"}',file=sys.stderr)
        raise SystemExit(1) from None
