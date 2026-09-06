"""Bounded one-shot historical execution/status tapes from the exact quote."""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import re
from decimal import Decimal
import zipfile

from momentumbot.research import sealed_historical_execution_quote_v01 as quote
from momentumbot.research.prospective_market_input_acquisition import _normalize_store
from momentumbot.research.prospective_market_input_capture import _quote_events, _status_events

CONTRACT_ID = 'sealed-historical-execution-input-acquisition-v0.1'
CONTRACT_PATH = f'research/strategy/{CONTRACT_ID}.json'
EXECUTION_PATH = f'research/strategy/{CONTRACT_ID}-execution.json'
WORKFLOW_PATH = '.github/workflows/sealed-historical-execution-input-acquisition-v01.yml'
CONSUMPTION_REF = f'refs/tags/{CONTRACT_ID}-consumed'
QUOTE_REPORT_PATH = 'research/data-audits/sealed-historical-execution-input-quote-v0.1-report-34066187628.json'
QUOTE_RUN_ID = 34066187628
QUOTE_ARTIFACT_ID = 9999061044
QUOTE_ZIP_SHA = '2a353b635407bffdb8076d88acdc520ad48f0bc19e28ff5d8c2e4ede8a88aa43'
QUOTE_REPORT_FILE_SHA = 'd2197b2c4319391f6f7164d414bfef9c8755a502069ecff410e1d6757ce45682'
QUOTE_REPORT_CONTENT_SHA = 'd74deaf49f63410da1452d494306dd07e22eedf3f572e3171d7c2ded34d18374'
MAX_BILLABLE_BYTES = 154456640
MAX_COST_USD = '0.172787457709'
MAX_RETAINED_BYTES = 1_000_000_000
MAX_UNCOMPRESSED_NORMALIZED_BYTES = 1_500_000_000
seal, write_json, file_sha, frozen = quote.seal, quote.write_json, quote.file_sha, quote.frozen


def contract() -> dict:
    return seal({
        'schema_version':1, 'contract_id':CONTRACT_ID,
        'artifact_type':'registered_quote_bound_historical_execution_input_acquisition',
        'parent_commit_sha':'20c500723b9062479191419a406d155c94b3ef6c',
        'parent_tree_sha':'ad8d498690e6a9fdaca60355d193f176866c865c',
        'quote_run_id':QUOTE_RUN_ID, 'quote_run_attempt':1, 'quote_artifact_id':QUOTE_ARTIFACT_ID,
        'quote_zip_sha256':QUOTE_ZIP_SHA, 'quote_report_file_sha256':QUOTE_REPORT_FILE_SHA,
        'quote_report_content_sha256':QUOTE_REPORT_CONTENT_SHA,
        'input_plan_inventory_sha256':quote.PLAN_INVENTORY_SHA256,
        'request_list_content_sha256':quote.REQUEST_LIST_SHA256,
        'date_count':30, 'opportunity_count':109, 'symbol_date_count':45, 'request_count':90,
        'maximum_requote_metadata_calls':180, 'maximum_timeseries_calls':90, 'maximum_http_attempts':270,
        'maximum_billable_bytes':MAX_BILLABLE_BYTES, 'maximum_quoted_cost_usd':MAX_COST_USD,
        'maximum_retained_normalized_tape_bytes':MAX_RETAINED_BYTES,
        'maximum_uncompressed_normalized_bytes':MAX_UNCOMPRESSED_NORMALIZED_BYTES,
        'per_request_wire_limit':'parent_quoted_billable_bytes_plus_65536_metadata_and_compression_overhead',
        'requote_gate':'all_90_complete_nonzero_and_both_aggregate_ceilings_not_exceeded_before_any_download',
        'download_gate':'one_exact_request_at_a_time_stop_on_first_failure_no_retry',
        'normalization':'unchanged_prospective_normalize_store_quote_events_and_status_events',
        'storage':'minimal_normalized_gzip_jsonl_tapes_and_receipts_only_delete_each_ephemeral_dbn',
        'partial_evidence':'retain_completed_tapes_receipts_and_sanitized_failure_no_partial_success',
        'consumption_ref':CONSUMPTION_REF, 'durable_consumption_before_provider_required':True,
        'sdk_version':quote.SDK_VERSION, 'python_version':'3.12.14',
        'requirements_path':quote.LOCK_PATH, 'requirements_sha256':quote.LOCK_SHA256,
        'redirects_allowed':False, 'automatic_retry_count':0,
        'provider_methods':['metadata.get_billable_size','metadata.get_cost','timeseries.get_range'],
        'account_or_fill_simulation_authorized':False, 'backtesting_authorized':False,
        'policy_change_authorized':False, 'retrospective_access_authorized':False,
        'next_gate':'independent_normalized_input_verification_then_provider_free_historical_capture_composition',
    })


def quote_parent(root: Path) -> dict:
    path = root / QUOTE_REPORT_PATH
    if file_sha(path) != QUOTE_REPORT_FILE_SHA:
        raise ValueError('exact independently verified quote report bytes changed')
    report = frozen(path)
    if report['content_sha256'] != QUOTE_REPORT_CONTENT_SHA or report['metadata_quote_gate_passed'] is not True:
        raise ValueError('successful quote prerequisite changed')
    if report['total_billable_size_bytes'] != MAX_BILLABLE_BYTES or report['total_quoted_cost_usd'] != MAX_COST_USD:
        raise ValueError('quote ceilings changed')
    return report


def validate_inputs(root: Path) -> tuple[list[dict], dict]:
    requests = quote.validate_inputs(root)
    quote.require_exact(frozen(root / CONTRACT_PATH), contract(), 'acquisition contract')
    parent = quote_parent(root)
    quote.validate_report(parent, requests, parent['provenance'])
    return requests, parent


def verify_quote_zip(path: Path, root: Path) -> None:
    if file_sha(path) != QUOTE_ZIP_SHA:
        raise ValueError('parent quote ZIP bytes changed')
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        expected = {'consumption.json','execution.json','contract.json','request-manifest.json','http-ledger.json','metadata-ledger.json','quote-report.json','quote-inventory.json'}
        if len(names) != len(expected) or set(names) != expected:
            raise ValueError('parent quote archive members changed')
        raw = {name:z.read(name) for name in names}
    inventory = json.loads(raw['quote-inventory.json'])
    if inventory['files'] != {name:hashlib.sha256(value).hexdigest() for name,value in raw.items() if name!='quote-inventory.json'}:
        raise ValueError('parent quote inventory differs')
    if raw['quote-report.json'] != (root / QUOTE_REPORT_PATH).read_bytes():
        raise ValueError('parent quote report differs')
    for value in raw.values():
        payload = json.loads(value)
        if payload['content_sha256'] != quote.canonical_fingerprint({k:v for k,v in payload.items() if k!='content_sha256'}):
            raise ValueError('parent quote JSON hash differs')


def execution_payload(*, code_commit: str, code_tree: str, workflow_sha256: str,
                      ci_run_id: str, validation_run_id: str) -> dict:
    # Reuse provenance format checks, without reusing the consumed quote identity.
    quote.execution_payload(code_commit=code_commit, code_tree=code_tree, workflow_sha256=workflow_sha256,
                            ci_run_id=ci_run_id, validation_run_id=validation_run_id)
    return seal({'schema_version':1,'execution_id':CONTRACT_ID+'-execution',
        'contract_content_sha256':contract()['content_sha256'],
        'code_commit_sha':code_commit,'code_tree_sha':code_tree,'workflow_path':WORKFLOW_PATH,
        'workflow_file_sha256':workflow_sha256,'code_ci_run_id':ci_run_id,'code_validation_run_id':validation_run_id,
        'repository':'RoomyRems/momentumbot','branch':'phase-3-historical-snapshot','event':'push','run_attempt':1,
        'consumption_ref':CONSUMPTION_REF,'quote_report_content_sha256':QUOTE_REPORT_CONTENT_SHA,
        'maximum_quoted_cost_usd':MAX_COST_USD,'maximum_billable_bytes':MAX_BILLABLE_BYTES,
        'authority':'user_authorized_continued_development_and_operational_steps_2026-09-06',
        'exact_quote_bound_acquisition_authorized':True,'account_or_order_authority':False})


def validate_execution(root: Path, env: dict) -> dict:
    value = frozen(root / EXECUTION_PATH)
    expected = execution_payload(code_commit=env.get('EXECUTION_CODE_COMMIT_SHA',''),
        code_tree=env.get('EXECUTION_CODE_TREE_SHA',''),workflow_sha256=file_sha(root / WORKFLOW_PATH),
        ci_run_id=value['code_ci_run_id'],validation_run_id=value['code_validation_run_id'])
    quote.require_exact(value,expected,'acquisition execution child')
    for key, item in {'GITHUB_REPOSITORY':'RoomyRems/momentumbot','GITHUB_EVENT_NAME':'push',
                      'GITHUB_REF':'refs/heads/phase-3-historical-snapshot','GITHUB_RUN_ATTEMPT':'1'}.items():
        if env.get(key) != item:
            raise ValueError('acquisition requires exact first research push')
    if not re.fullmatch('[0-9a-f]{40}',env.get('GITHUB_SHA','')) or not re.fullmatch('[1-9][0-9]+',env.get('GITHUB_RUN_ID','')):
        raise ValueError('full acquisition run provenance required')
    return value


def consumption(execution: dict, env: dict) -> dict:
    return seal({'execution_content_sha256':execution['content_sha256'],'consumption_ref':CONSUMPTION_REF,
        'execution_commit_sha':env['GITHUB_SHA'],'workflow_run_id':env['GITHUB_RUN_ID'],'workflow_run_attempt':1,
        'quote_zip_sha256':QUOTE_ZIP_SHA,'quote_report_content_sha256':QUOTE_REPORT_CONTENT_SHA})


def preflight(requests: list[dict], calls: list[dict], *, provenance: dict,
              http_attempts: int, blocked_attempts: int) -> dict:
    result = quote.build_report(requests,calls,provenance=provenance,http_attempts=http_attempts,blocked_attempts=blocked_attempts)
    quote.validate_report(result,requests,provenance)
    passed = (result['metadata_quote_gate_passed'] and result['total_billable_size_bytes'] <= MAX_BILLABLE_BYTES
              and Decimal(result['total_quoted_cost_usd']) <= Decimal(MAX_COST_USD))
    return seal({'contract_id':CONTRACT_ID,'artifact_type':'historical_execution_acquisition_metadata_requote',
        'parent_quote_report_content_sha256':QUOTE_REPORT_CONTENT_SHA,'metadata_result':result,
        'maximum_billable_bytes':MAX_BILLABLE_BYTES,'maximum_quoted_cost_usd':MAX_COST_USD,
        'preflight_passed':passed})


def normalize(store, request: dict) -> list[dict]:
    records = _normalize_store(store,request)
    if not records:
        raise ValueError('missing exact request records')
    if request['schema'] == 'mbp-1':
        _quote_events(records)
    else:
        _status_events(records)
    return records


def write_tape(path: Path, records: list[dict]) -> dict:
    digest = hashlib.sha256()
    count = 0
    byte_count = 0
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:
        with gzip.GzipFile(filename='',mode='wb',fileobj=stream,mtime=0) as zipped:
            for record in records:
                raw = (json.dumps(record,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
                byte_count += len(raw)
                if byte_count > MAX_UNCOMPRESSED_NORMALIZED_BYTES:
                    raise ValueError('normalized retention ceiling exceeded')
                digest.update(raw); zipped.write(raw); count += 1
    return {'row_count':count,'normalized_bytes':byte_count,'normalized_sha256':digest.hexdigest(),
            'file_bytes':path.stat().st_size,'file_sha256':file_sha(path)}


def acquire_tapes(requests: list[dict], preflight_result: dict, *, client, output: Path,
                  temporary_root: Path, progress=None) -> list[dict]:
    quote.validate_requests(requests)
    expected = preflight(requests,preflight_result['metadata_result']['calls'],
        provenance=preflight_result['metadata_result']['provenance'],
        http_attempts=preflight_result['metadata_result']['http_attempts'],
        blocked_attempts=preflight_result['metadata_result']['blocked_attempts'])
    quote.require_exact(preflight_result,expected,'complete acquisition preflight')
    if preflight_result['preflight_passed'] is not True:
        raise ValueError('quote or byte/cost ceiling blocks every download')
    rows = []
    retained = normalized = 0
    for index, request in enumerate(requests):
        raw_path = temporary_root / f'request-{index:03d}.dbn.zst'
        tape = output / 'tapes' / f'request-{index:03d}.jsonl.gz'
        row = {'ordinal':index+1,'request_id':request['request_id'],
               'request_content_sha256':quote.canonical_fingerprint(request),'schema':request['schema'],
               'status':'pending','error':None,'failure_stage':None,'tape':None,'ephemeral_dbn_sha256':None}
        rows.append(row)
        if progress: progress(seal({'requests':rows,'complete':False}))
        stage = 'timeseries_request'
        try:
            store = client.get_range(path=str(raw_path),**quote.request_kwargs(request))
            stage = 'ephemeral_dbn_validation'
            if not raw_path.is_file() or raw_path.stat().st_size == 0:
                raise ValueError('missing ephemeral DBN')
            raw_hash = file_sha(raw_path)
            row['ephemeral_dbn_sha256'] = raw_hash
            stage = 'normalization'
            records = normalize(store,request)
            stage = 'normalized_tape_write'
            tape_result = write_tape(tape,records)
            retained += tape_result['file_bytes']; normalized += tape_result['normalized_bytes']
            stage = 'normalized_retention_ceiling'
            if retained > MAX_RETAINED_BYTES or normalized > MAX_UNCOMPRESSED_NORMALIZED_BYTES:
                raise ValueError('aggregate normalized retention ceiling exceeded')
            row.update(status='complete',ephemeral_dbn_sha256=raw_hash,
                       tape={'path':tape.relative_to(output).as_posix(),**tape_result})
            stage = 'completion_receipt_write'
            write_json(output / 'receipts' / f'request-{index:03d}.json',seal({
                'contract_id':CONTRACT_ID,'request':request,'completion':row,
                'metadata_verified':True,'raw_dbn_persisted':False}))
        except quote.MetadataFailure as exc:
            row.update(status='failed',error=exc.code,failure_stage=stage)
        except Exception:
            row.update(status='failed',error='download_or_normalization_failed',failure_stage=stage)
        finally:
            raw_path.unlink(missing_ok=True)
            if row['status'] != 'complete':
                tape.unlink(missing_ok=True)
            if progress: progress(seal({'requests':rows,'complete':len(rows)==90 and all(r['status']=='complete' for r in rows)}))
        if row['status'] != 'complete':
            break
    return rows
