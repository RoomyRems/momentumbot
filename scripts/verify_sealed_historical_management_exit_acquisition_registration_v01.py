"""Independent stdlib checks of exit acquisition registration and retained evidence.

This checker imports no MomentumBot code and makes no provider requests. Optional
capture checks cover inventory, receipt/tape bytes, population and ordering;
native schema semantics remain the responsibility of the frozen primary verifier.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
import zipfile

ID = 'sealed-historical-management-exit-acquisition-v0.1'
QUOTE = 'sealed-historical-management-exit-quote-v0.1'
PLAN = 'research/runtime/sealed-historical-management-runner-v0.1/exit-input-request-plan.json'
QUOTE_SHA = '85c4989a32ddb325ea70e280a43bdc31cc6e8e5f82eb41a10586901ee388196a'
AUDIT_SHA = '1423e00a1feced569a54a9078190410f6786188d2a24866718823978c90ace8a'
REQUEST_SHA = '973a926e063fda7ec76883dd4297b88c77a06af22fe3bc0618330e98e28825b4'
PARENT = '0d36c619dc1d3ac8c50bf7fa91201114255e696c'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def same(left, right):
    require(canonical(left) == canonical(right), 'exact typed value differs')


def read(path):
    require(path.is_file() and not path.is_symlink(), 'regular metadata required')
    value = json.loads(path.read_bytes())
    same(value['content_sha256'], digest(canonical({k:v for k,v in value.items() if k != 'content_sha256'})))
    return value


def check(root, archives=None, capture=None):
    contract = read(root/f'research/strategy/{ID}.json')
    limits = read(root/f'research/runtime/{ID}/request-limits.json')
    manifest = read(root/f'research/runtime/{QUOTE}/request-manifest.json')
    quoted_path = root/f'research/data-audits/{QUOTE}-report-34169338681.json'
    audit_path = root/f'research/data-audits/{QUOTE}-independent-verification-34169338681.json'
    same(digest(quoted_path.read_bytes()), QUOTE_SHA)
    same(digest(audit_path.read_bytes()), AUDIT_SHA)
    quoted, audit, plan = read(quoted_path), read(audit_path), read(root/PLAN)
    requests = manifest['requests']
    same(digest(canonical(requests)), REQUEST_SHA)
    same(len(requests), 80)
    same(len(plan['opportunities']), 109)
    same(sum(o['entry_input_status'] == 'unavailable' for o in plan['opportunities']), 23)
    same(contract['parent_commit_sha'], PARENT)
    same(contract['new_request_indices'], list(range(80)))
    same((contract['maximum_metadata_attempts'], contract['maximum_timeseries_attempts'], contract['maximum_http_attempts']), (160, 80, 240))
    for name, sha in contract['frozen_file_sha256'].items():
        same(digest((root/name).read_bytes()), sha)
    rows = []
    for i, (request, quote) in enumerate(zip(requests, quoted['quote_rows'], strict=True)):
        same(request['request_id'], quote['request_id'])
        require(request['symbols'] != ['XAGE'], 'verified XAGE cannot be acquired again')
        require(type(quote['billable_size_bytes']) is int and quote['billable_size_bytes'] > 0, 'positive exact size required')
        require(Decimal(quote['quoted_cost_usd']).is_finite(), 'finite quote required')
        rows.append({'exit_request_index': i, 'request': request,
            'request_content_sha256': digest(canonical(request)),
            'maximum_billable_bytes': quote['billable_size_bytes'],
            'maximum_quoted_cost_usd': quote['quoted_cost_usd'],
            'maximum_wire_bytes': quote['billable_size_bytes'] + 65536})
    same(limits['request_limits'], rows)
    total = sum(row['maximum_billable_bytes'] for row in rows)
    cost = format(sum((Decimal(row['maximum_quoted_cost_usd']) for row in rows), Decimal(0)), 'f')
    same((total, cost), (209898320, '0.234732925899'))
    for value in (limits, contract):
        same((value['maximum_billable_bytes'], value['maximum_quoted_cost_usd']), (total, cost))
        same(value['quote_report_content_sha256'], quoted['content_sha256'])
    for flag in ('acquisition_gate_passed', 'runtime_input_eligible', 'historical_execution_authorized',
                 'backtesting_executed', 'account_or_fill_simulation_executed', 'retrospective_inputs_loaded', 'policy_changed'):
        same(contract[flag], False)
    archive_counts = {}
    if archives is not None:
        for name, spec in contract['parent_artifacts'].items():
            path = archives/name
            same((path.stat().st_size, digest(path.read_bytes())), (spec['bytes'], spec['sha256']))
            with zipfile.ZipFile(path) as archive:
                files = {}
                for member in archive.infolist():
                    if member.is_dir():
                        continue
                    require(member.filename not in files, 'duplicate archive member')
                    raw = archive.read(member)
                    files[member.filename] = {'bytes': len(raw), 'sha256': digest(raw)}
                same(files, audit['independent_quote_verification']['archives'][spec['kind']]['files'])
                if spec['kind'] == 'result':
                    same(digest(archive.read('quote-report.json')), QUOTE_SHA)
                archive_counts[name] = len(files)
    capture_result = None
    if capture is not None:
        report, inventory = read(capture/'capture-report.json'), read(capture/'capture-inventory.json')
        files = {}
        for path in sorted(capture.rglob('*')):
            require(not path.is_symlink(), 'capture symlink')
            if path.is_file() and path.name != 'capture-inventory.json':
                files[path.relative_to(capture).as_posix()] = {'bytes': path.stat().st_size, 'sha256': digest(path.read_bytes())}
                if path.suffix == '.json':
                    read(path)
        same(files, inventory['files'])
        same(report['original_opportunities'], plan['opportunities'])
        same(read(capture/'download-ledger.json')['requests'], report['requests'])
        same(len(report['coverage']), 80)
        totals = {'complete': 0, 'unavailable': 0, 'failed': 0, 'unattempted': 80-len(report['requests'])}
        normalized = 0
        for i, row in enumerate(report['requests']):
            request = requests[i]
            same((row['exit_request_index'], row['ordinal'], row['request_id'], row['request_content_sha256']),
                 (i, i+1, request['request_id'], digest(canonical(request))))
            totals[row['status']] += 1
            same(report['coverage'][i]['status'], row['status'])
            if row['status'] == 'failed':
                same(i, len(report['requests'])-1)
                same(row['tape'], None)
                continue
            receipt = read(capture/f'receipts/request-{i:03d}.json')
            same(receipt['request'], request)
            same(receipt['completion'], row)
            if row['status'] == 'unavailable':
                same(row['native']['native_record_count'], 0)
                same(row['tape'], None)
                require(not (capture/f'tapes/request-{i:03d}.jsonl.gz').exists(), 'unavailable empty tape')
                continue
            path = capture/row['tape']['path']
            with gzip.open(path, 'rb') as stream:
                raw = stream.read(1500000001)
            require(len(raw) <= 1500000000, 'normalized bound exceeded')
            records = [json.loads(line) for line in raw.splitlines()]
            same(raw.decode(), ''.join(canonical(record).decode()+'\n' for record in records))
            same(row['tape'], {'path': f'tapes/request-{i:03d}.jsonl.gz', 'file_bytes': path.stat().st_size,
                'file_sha256': digest(path.read_bytes()), 'normalized_bytes': len(raw),
                'normalized_sha256': digest(raw), 'row_count': len(records)})
            same(row['native']['native_record_count'], len(records))
            for record in records:
                same(record['symbol'], request['symbols'][0])
                require(request['start_ns'] <= record['ts_recv_ns'] < request['end_ns'], 'record outside request')
            if request['schema'] == 'mbp-1':
                same([record['source_record_index'] for record in records], list(range(len(records))))
                same([record['source_request_sha256'] for record in records], [digest(canonical(request))]*len(records))
                keys = [(record['ts_recv_ns'], record['sequence']) for record in records]
            else:
                keys = [record['ts_recv_ns'] for record in records]
            same(keys, sorted(keys))
            normalized += len(raw)
        same((report['new_complete_count'], report['new_unavailable_count'], report['unattempted_count']),
             (totals['complete'], totals['unavailable'], totals['unattempted']))
        for i in range(len(report['requests']), 80):
            same(report['coverage'][i]['status'], 'unattempted')
        counts = []
        for name, cap in (('metadata-http-ledger.json', 160), ('timeseries-http-ledger.json', 80)):
            ledger = read(capture/name)
            require(type(ledger['http_attempts']) is int and 0 <= ledger['http_attempts'] <= cap, 'HTTP bound')
            same(ledger['http_attempts'], len(ledger['attempts']))
            same(ledger['automatic_retries'], 0)
            same(ledger['redirects_followed'], 0)
            for i, attempt in enumerate(ledger['attempts']):
                same(attempt['ordinal'], i+1)
                same(attempt['request_id'], requests[i//2 if cap == 160 else i]['request_id'])
            counts.append(ledger['http_attempts'])
        same(report['http_attempts'], sum(counts))
        same(report['acquisition_gate_passed'], False)
        same(report['historical_execution_authorized'], False)
        capture_result = {'counts': totals, 'http_attempts': sum(counts), 'normalized_bytes': normalized,
            'file_count': len(files)+1, 'report_content_sha256': report['content_sha256'],
            'request_evidence_complete': report['request_evidence_complete']}
    return {'verification_passed': True, 'contract_content_sha256': contract['content_sha256'],
        'limits_content_sha256': limits['content_sha256'], 'request_count': 80,
        'maximum_billable_bytes': total, 'maximum_quoted_cost_usd': cost,
        'archive_file_counts': archive_counts, 'capture': capture_result,
        'execution_record_present': (root/f'research/strategy/{ID}-execution.json').exists(),
        'provider_calls': 0, 'production_verifier_imported': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--archives', type=Path)
    parser.add_argument('--capture', type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.root, args.archives, args.capture), sort_keys=True))


if __name__ == '__main__':
    main()
