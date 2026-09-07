"""Verify parents, consume once, then acquire only the unattempted exact suffix."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from run_offline_python_v13 import deny_external_io
from momentumbot.research import sealed_historical_execution_acquisition_v03 as acq
from momentumbot.research import sealed_historical_execution_transport_v03 as transport

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--validate-only', action='store_true')
    mode.add_argument('--consume', action='store_true')
    mode.add_argument('--acquire', action='store_true')
    parser.add_argument('--check-environment', action='store_true')
    parser.add_argument('--check-execution', action='store_true')
    parser.add_argument('--preflight-root', type=Path)
    parser.add_argument('--output-root', type=Path)
    args = parser.parse_args()
    if not args.acquire: sys.addaudithook(deny_external_io)
    requests, quoted = acq.validate_inputs(ROOT)
    if args.check_environment or args.check_execution or args.consume or args.acquire:
        environment = acq.parent.environment(ROOT)
    if args.check_execution or args.consume or args.acquire:
        execution = acq.validate_execution(ROOT, os.environ)
    if args.validate_only:
        print(json.dumps({'valid': True, 'new_requests': 65, 'inherited_complete': 24,
            'inherited_unavailable': 1, 'maximum_http_attempts': 195, 'provider_calls': 0})); return 0
    pre = args.preflight_root
    if pre is None: parser.error('preflight root required')
    parents = acq.verify_parents(pre, ROOT)
    expected = acq.consumption(execution, os.environ)
    if args.consume:
        ref = json.loads((pre/'consumption-ref.json').read_text())
        if ref.get('ref') != acq.CONSUMPTION_REF or ref.get('object', {}).get('sha') != os.environ['GITHUB_SHA']:
            raise ValueError('durable exact consumption ref required')
        for name, value in (('consumption.json', expected), ('environment.json', environment), ('parent-verification.json', parents)):
            acq.write_json(pre/name, value)
        for path, name in ((ROOT/acq.EXECUTION_PATH, 'execution.json'), (ROOT/acq.CONTRACT_PATH, 'contract.json')):
            shutil.copyfile(path, pre/name)
        return 0
    acq.quote.require_exact(acq.frozen(pre/'consumption.json'), expected, 'durable consumption')
    acq.quote.require_exact(acq.frozen(pre/'environment.json'), environment, 'durable environment')
    acq.quote.require_exact(acq.frozen(pre/'parent-verification.json'), parents, 'durable parent verification')
    output = args.output_root
    if output is None: parser.error('output root required')
    if output.exists() or output.is_symlink(): raise ValueError('new write-once result directory required')
    output.mkdir(parents=True)
    for name in (*acq.PARENT_ARTIFACTS, 'consumption.json', 'environment.json', 'parent-verification.json', 'execution.json', 'contract.json'):
        shutil.copyfile(pre/name, output/name)
    provenance = {'execution_commit_sha': os.environ['GITHUB_SHA'], 'workflow_run_id': os.environ['GITHUB_RUN_ID'],
        'workflow_run_attempt': 1, 'code_commit_sha': execution['code_commit_sha'], 'code_tree_sha': execution['code_tree_sha'],
        'execution_content_sha256': execution['content_sha256'], 'consumption_content_sha256': expected['content_sha256']}
    metadata = acq.seal({'http_attempts': 0, 'blocked_attempts': 0, 'attempts': [],
        'automatic_retries': 0, 'redirects_followed': 0, 'non_metadata_calls': 0})
    timeseries = acq.seal({'http_attempts': 0, 'blocked_attempts': 0, 'attempts': [],
        'automatic_retries': 0, 'redirects_followed': 0, 'unregistered_endpoint_calls': 0})
    for name, value in (('metadata-http-ledger.json', metadata), ('timeseries-http-ledger.json', timeseries),
        ('metadata-ledger.json', acq.seal({'calls': []})), ('download-ledger.json', acq.download_ledger([]))):
        acq.write_json(output/name, value)
    key = os.environ.get('DATABENTO_API_KEY', '')
    session = mtransport = ttransport = None
    rows, requote, error = [], None, None
    try:
        if not key: raise ValueError('credential_missing')
        import databento
        import requests as http
        if databento.__version__ != acq.quote.SDK_VERSION: raise ValueError('sdk_version_mismatch')
        session = http.Session(); session.trust_env = False
        mtransport = transport.MetadataOnlyHTTP(requests, session=session, key=key,
            progress=lambda value: acq.write_json(output/'metadata-http-ledger.json', value, replace=True))
        calls = acq.collect_quote(requests, transport.sdk_metadata(mtransport),
            progress=lambda value: acq.write_json(output/'metadata-ledger.json', value, replace=True))
        requote = acq.preflight(requests, quoted, calls, len(mtransport.attempts), mtransport.blocked)
        acq.write_json(output/'requote-report.json', requote)
        if not requote['preflight_passed']:
            error = 'requote_unavailable_or_ceiling_exceeded'
        else:
            with tempfile.TemporaryDirectory(prefix='historical-execution-v03-') as temp:
                temporary = Path(temp)
                ttransport = transport.ExactTimeseriesHTTP(requests, quoted, requote, session=session, key=key, temporary_root=temporary,
                    progress=lambda value: acq.write_json(output/'timeseries-http-ledger.json', value, replace=True))
                rows = acq.acquire_tapes(requests, quoted, requote, client=transport.sdk_timeseries(ttransport), output=output,
                    temporary_root=temporary, progress=lambda value: acq.write_json(output/'download-ledger.json', value, replace=True))
                if any(temporary.iterdir()): raise ValueError('raw_cleanup_failed')
            if not acq.download_ledger(rows)['evidence_complete']: error = 'download_or_normalization_failed'
    except Exception:
        error = 'credential_missing' if not key else 'acquisition_runtime_failed'
        rows = acq.frozen(output/'download-ledger.json')['requests']
    finally:
        if session is not None: session.close()
        if mtransport is not None: mtransport.save(); metadata = mtransport.ledger()
        if ttransport is not None: ttransport.save(); timeseries = ttransport.ledger()
        report = acq.build_report(rows, metadata, timeseries, requote, provenance, ROOT, error)
        if key and key in json.dumps(report, sort_keys=True): raise ValueError('sanitized serialization rejected')
        acq.write_json(output/'capture-report.json', report)
        acq.write_inventory(output, report)
    try:
        acq.verify_capture(output, ROOT)
    except Exception:
        report = acq.build_report(rows, metadata, timeseries, requote, provenance, ROOT, 'post_capture_verification_failed')
        acq.write_json(output/'capture-report.json', report, replace=True)
        acq.write_inventory(output, report, replace=True)
    print(json.dumps({k: report[k] for k in ('request_evidence_complete', 'new_complete_count', 'new_unavailable_count',
        'unattempted_count', 'http_attempts', 'blocked_attempts', 'acquisition_gate_passed', 'error')}))
    return 0 if report['request_evidence_complete'] else 1


if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception:
        print('{"status":"failed","sanitized_error":"remaining exact acquisition validation failed"}', file=sys.stderr)
        raise SystemExit(1) from None
