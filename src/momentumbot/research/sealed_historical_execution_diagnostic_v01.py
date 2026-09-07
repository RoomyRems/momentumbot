"""One-request diagnostic of the immutable historical v0.1 normalization failure.

This child never produces a runtime input tape or changes the parent validator.
Only fixed diagnostic codes and a bounded, typed field projection are retained.
"""
from __future__ import annotations

from decimal import Decimal
import gzip
import hashlib
import json
import operator
from pathlib import Path
import re
import zipfile

from momentumbot.research import sealed_historical_execution_acquisition_v01 as parent
from momentumbot.research import sealed_historical_execution_quote_v01 as quote
from momentumbot.research.prospective_market_input_acquisition import (
    _mapped_frame, _metadata_field, _metadata_timestamp_ns, _metadata_value,
    _normalize_store,
)

CONTRACT_ID = 'sealed-historical-execution-input-diagnostic-v0.1'
CONTRACT_PATH = f'research/strategy/{CONTRACT_ID}.json'
EXECUTION_PATH = f'research/strategy/{CONTRACT_ID}-execution.json'
WORKFLOW_PATH = '.github/workflows/sealed-historical-execution-input-diagnostic-v01.yml'
CONSUMPTION_REF = f'refs/tags/{CONTRACT_ID}-consumed'
FAILURE_RUN_ID = 34067754001
FAILURE_ARTIFACT_ID = 9999544369
FAILURE_ZIP_SHA = '90d9a52c04acbf3482a716e08ba4f66cb1e0a601ceb76fbb22de02a9ae424285'
FAILURE_REPORT_PATH = 'research/data-audits/sealed-historical-execution-input-acquisition-v0.1-report-34067754001.json'
FAILURE_REPORT_FILE_SHA = '4a60754567cd39b4a31ab222526ef4326000ea82eb9e252dce3897840c143f1c'
FAILURE_REPORT_SHA = '907b2dc18ed6f04a9b5562a4bd08889b69bf171fcd62cea3b06587ca0daaf3d9'
FAILURE_AUDIT_PATH = 'research/data-audits/sealed-historical-execution-input-acquisition-v0.1-independent-verification-34067754001.json'
FAILURE_AUDIT_FILE_SHA = 'a09b54b15908ade00637aedba548c2231b3a7be10c62d92a259902a0a70a562b'
FAILURE_AUDIT_SHA = '613e1cde55d7d5c2d3272d4669e4bf2fcc2055a86e1c151abdb55359cb28996a'
REQUEST_SHA = 'be03937b8eb8af38764d3203fbeebd7f360eeacfd21e92ae0d14e3f4ebf8ab9a'
PRIOR_DBN_SHA = 'be5e196dc30d08ecc9b9140bafe160a77aeec5347b14bcb9f4cbcb6f436b1dc9'
MAX_BILLABLE_BYTES = 1_975_840
MAX_COST_USD = '0.002208173275'
MAX_WIRE_BYTES = MAX_BILLABLE_BYTES + 65536
MAX_ROWS = 50_000
MAX_PROJECTION_BYTES = 64_000_000
MAX_RETAINED_PROJECTION_BYTES = 16_000_000
FROZEN_CODE = {
    'src/momentumbot/research/sealed_historical_execution_acquisition_v01.py':'ca57499aee9c5ebd7b53230c04574257cfef9b0586859e1c7ecd529871638f05',
    'src/momentumbot/research/prospective_market_input_acquisition.py':'5f1e354ae74512c03f78413b9e19b753ecc210083f41460468f124d1a23fcfae',
    'src/momentumbot/research/prospective_market_input_capture.py':'7b736e329a9d12eb2dfdeb09473fd04fc1caa0416eb1cb84ff2db7f4819ae9ee',
    '.github/workflows/sealed-historical-execution-input-acquisition-v01.yml':'5b0f85f776de813862e53cdf3335815a3a0b554e5f3aa375aecbec8f78750c02',
    'src/momentumbot/research/sealed_historical_execution_transport_v01.py':'3df2150f8970d1a6199cdf2bfcd5bcdfc35970e4257c90b54b8754218bdd91a3',
    'scripts/acquire_sealed_historical_execution_inputs_v01.py':'ec4ccb7b73065717be85e4d0af9cbbfc4d704872555b3d167c87c55b2a784841',
    'research/strategy/sealed-historical-execution-input-acquisition-v0.1-execution.json':'c751ab5610f51332a7eb6745f30550dd5ed8b8cced4fb1ef09549df0ebfff5d1',
}
FIELDS = ('symbol','ts_recv','sequence','bid_px_00','bid_sz_00','ask_px_00','ask_sz_00',
          'ts_event','instrument_id','publisher_id','flags','action','side','depth')
SAFE_TEXT = frozenset({'GITS','XNAS.ITCH','xnas.itch','mbp-1','status','raw_symbol',
    'raw-symbol','instrument_id','instrument-id','A','C','M','R','T','F','N','B','S','Y','~'})
seal, write_json, file_sha, frozen = quote.seal, quote.write_json, quote.file_sha, quote.frozen


def request() -> dict:
    return {'dataset':'XNAS.ITCH','schema':'mbp-1','symbols':['GITS'],'stype_in':'raw_symbol',
            'trading_date':'2025-05-30','request_id':'2025-05-30-GITS-mbp-1',
            'start_ns':1748609823047734566,'end_ns':1748609850749660996,'end_exclusive':True}


def contract() -> dict:
    return seal({'schema_version':1,'contract_id':CONTRACT_ID,
        'artifact_type':'registered_single_request_normalization_diagnostic',
        'parent_commit_sha':'f678b83525145a501490cec4606bac4dcbc591e7',
        'parent_tree_sha':'fa67b8a4ccc55c0f57175c2c335923a1ee8a3217',
        'failure_run_id':FAILURE_RUN_ID,'failure_run_attempt':1,'failure_artifact_id':FAILURE_ARTIFACT_ID,
        'failure_zip_sha256':FAILURE_ZIP_SHA,'failure_report_content_sha256':FAILURE_REPORT_SHA,
        'failure_report_file_sha256':FAILURE_REPORT_FILE_SHA,'failure_audit_content_sha256':FAILURE_AUDIT_SHA,
        'failure_audit_file_sha256':FAILURE_AUDIT_FILE_SHA,'prior_ephemeral_dbn_sha256':PRIOR_DBN_SHA,
        'request':request(),'request_content_sha256':REQUEST_SHA,'request_count':1,
        'original_request_list_content_sha256':quote.REQUEST_LIST_SHA256,
        'parent_quote_report_content_sha256':parent.QUOTE_REPORT_CONTENT_SHA,
        'maximum_metadata_calls':2,'maximum_timeseries_calls':1,'maximum_http_attempts':3,
        'maximum_billable_bytes':MAX_BILLABLE_BYTES,'maximum_quoted_cost_usd':MAX_COST_USD,
        'maximum_wire_bytes':MAX_WIRE_BYTES,'maximum_projection_rows':MAX_ROWS,
        'maximum_projection_bytes':MAX_PROJECTION_BYTES,
        'maximum_retained_projection_bytes':MAX_RETAINED_PROJECTION_BYTES,
        'preflight':'both_fresh_exact_nonzero_size_and_cost_at_or_below_original_first_request_ceilings',
        'frozen_code_file_sha256':FROZEN_CODE,'normalization':'execute_unchanged_parent_normalize_once',
        'diagnostic_projection_fields':list(FIELDS),
        'diagnostic_projection':'original_order_typed_fields_only_unknown_text_hashed_no_provider_exception_text',
        'raw_dbn_retention':'ephemeral_hash_then_delete_in_finally',
        'diagnostic_success':'complete_bounded_evidence_independently_verified_not_input_gate',
        'runtime_input_eligible':False,'acquisition_gate_passed':False,
        'normalization_repair_authorized':False,'account_or_fill_simulation_authorized':False,
        'backtesting_authorized':False,'retrospective_access_authorized':False,'policy_change_authorized':False,
        'sdk_version':quote.SDK_VERSION,'python_version':'3.12.14',
        'requirements_path':quote.LOCK_PATH,'requirements_sha256':quote.LOCK_SHA256,
        'automatic_retry_count':0,'redirects_allowed':False,'consumption_ref':CONSUMPTION_REF,
        'durable_consumption_before_provider_required':True,
        'next_gate':'independent_diagnosis_then_separately_versioned_normalization_child_if_supported'})


def validate_inputs(root: Path) -> dict:
    requests, quoted = parent.validate_inputs(root)
    quote.require_exact(requests[0],request(),'exact failed request')
    if quote.canonical_fingerprint(request()) != REQUEST_SHA:
        raise ValueError('diagnostic request differs')
    first = quoted['quote_rows'][0]
    if first['billable_size_bytes'] != MAX_BILLABLE_BYTES or first['quoted_cost_usd'] != MAX_COST_USD:
        raise ValueError('original first request quote ceilings differ')
    for path, sha in {**FROZEN_CODE, FAILURE_AUDIT_PATH:FAILURE_AUDIT_FILE_SHA,
                      FAILURE_REPORT_PATH:FAILURE_REPORT_FILE_SHA}.items():
        if file_sha(root / path) != sha:
            raise ValueError('immutable parent bytes differ')
    audit, report = frozen(root / FAILURE_AUDIT_PATH), frozen(root / FAILURE_REPORT_PATH)
    if audit['content_sha256'] != FAILURE_AUDIT_SHA or report['content_sha256'] != FAILURE_REPORT_SHA:
        raise ValueError('immutable failure content differs')
    quote.require_exact(frozen(root / CONTRACT_PATH),contract(),'diagnostic contract')
    return request()


def verify_failure_zip(path: Path, root: Path) -> None:
    if file_sha(path) != FAILURE_ZIP_SHA:
        raise ValueError('exact failed acquisition ZIP differs')
    expected = frozen(root / FAILURE_AUDIT_PATH)['artifacts']['result']['files']
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if len(names) != len(expected) or set(names) != set(expected):
            raise ValueError('failed acquisition archive members differ')
        for name in names:
            raw = z.read(name)
            if {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()} != expected[name]:
                raise ValueError('failed acquisition archive file differs')
            payload = json.loads(raw)
            quote.require_exact(payload,seal({k:v for k,v in payload.items() if k!='content_sha256'}),'failure JSON')
        if z.read('capture-report.json') != (root / FAILURE_REPORT_PATH).read_bytes():
            raise ValueError('failed acquisition report differs')


def execution_payload(*, code_commit: str, code_tree: str, workflow_sha256: str,
                      ci_run_id: str, validation_run_id: str) -> dict:
    quote.execution_payload(code_commit=code_commit,code_tree=code_tree,workflow_sha256=workflow_sha256,
                            ci_run_id=ci_run_id,validation_run_id=validation_run_id)
    return seal({'execution_id':CONTRACT_ID+'-execution','contract_content_sha256':contract()['content_sha256'],
        'code_commit_sha':code_commit,'code_tree_sha':code_tree,'workflow_file_sha256':workflow_sha256,
        'workflow_path':WORKFLOW_PATH,'code_ci_run_id':ci_run_id,'code_validation_run_id':validation_run_id,
        'repository':'RoomyRems/momentumbot','branch':'phase-3-historical-snapshot','event':'push','run_attempt':1,
        'consumption_ref':CONSUMPTION_REF,'request_content_sha256':REQUEST_SHA,
        'failure_zip_sha256':FAILURE_ZIP_SHA,'maximum_quoted_cost_usd':MAX_COST_USD,
        'maximum_billable_bytes':MAX_BILLABLE_BYTES,'maximum_http_attempts':3,
        'authority':'user_authorized_continued_development_and_operational_steps_2026-09-06',
        'single_request_diagnostic_authorized':True,'account_or_order_authority':False})


def validate_execution(root: Path, env: dict) -> dict:
    value = frozen(root / EXECUTION_PATH)
    expected = execution_payload(code_commit=env.get('EXECUTION_CODE_COMMIT_SHA',''),
        code_tree=env.get('EXECUTION_CODE_TREE_SHA',''),workflow_sha256=file_sha(root / WORKFLOW_PATH),
        ci_run_id=value['code_ci_run_id'],validation_run_id=value['code_validation_run_id'])
    quote.require_exact(value,expected,'diagnostic sole execution child')
    for key, item in {'GITHUB_REPOSITORY':'RoomyRems/momentumbot','GITHUB_EVENT_NAME':'push',
                      'GITHUB_REF':'refs/heads/phase-3-historical-snapshot','GITHUB_RUN_ATTEMPT':'1'}.items():
        if env.get(key) != item:
            raise ValueError('diagnostic requires exact first research push')
    if not re.fullmatch('[0-9a-f]{40}',env.get('GITHUB_SHA','')) or not re.fullmatch('[1-9][0-9]+',env.get('GITHUB_RUN_ID','')):
        raise ValueError('exact diagnostic provenance required')
    return value


def consumption(execution: dict, env: dict) -> dict:
    return seal({'execution_content_sha256':execution['content_sha256'],'consumption_ref':CONSUMPTION_REF,
        'execution_commit_sha':env['GITHUB_SHA'],'workflow_run_id':env['GITHUB_RUN_ID'],'workflow_run_attempt':1,
        'failure_zip_sha256':FAILURE_ZIP_SHA,'request_content_sha256':REQUEST_SHA})


def preflight(calls: list[dict], http_attempts: int, blocked_attempts: int) -> dict:
    good = len(calls) == 2 and http_attempts == 2 and blocked_attempts == 0
    values = []
    for i, row in enumerate(calls):
        if i >= 2 or row.get('method') != quote.METHODS[i] or row.get('request_content_sha256') != REQUEST_SHA or row.get('ordinal') != i+1:
            raise ValueError('diagnostic metadata call identity differs')
        if set(row) != {'ordinal','method','request_content_sha256','status','value','error'}:
            raise ValueError('diagnostic metadata fields differ')
        if row['status'] == 'success' and row['error'] is None:
            values.append(quote._value(row['method'],row['value']))
        else:
            good = False
    if good:
        good = 0 < values[0] <= MAX_BILLABLE_BYTES and Decimal(values[1]) <= Decimal(MAX_COST_USD)
    return seal({'contract_id':CONTRACT_ID,'request_content_sha256':REQUEST_SHA,'calls':calls,
        'http_attempts':http_attempts,'blocked_attempts':blocked_attempts,'preflight_passed':good,
        'maximum_billable_bytes':MAX_BILLABLE_BYTES,'maximum_quoted_cost_usd':MAX_COST_USD})


ERROR_CODES = {
    'download metadata dataset mismatch':'metadata_dataset_mismatch',
    'download metadata schema mismatch':'metadata_schema_mismatch',
    'download metadata input symbology mismatch':'metadata_stype_mismatch',
    'download metadata symbols mismatch':'metadata_symbols_mismatch',
    'download metadata start mismatch':'metadata_start_mismatch',
    'download metadata end mismatch':'metadata_end_mismatch',
    'download metadata start is timezone-naive':'metadata_start_naive',
    'download metadata end is timezone-naive':'metadata_end_naive',
    'provider record mapping failed':'record_mapping_failed',
    'mapped provider frame lacks ts_recv or symbol':'mapped_frame_identity_fields_missing',
    'mapped provider frame lacks required schema fields':'mapped_frame_schema_fields_missing',
    'mapped provider record symbol differs from request':'record_symbol_mismatch',
    'mapped provider record falls outside exact request':'record_outside_request',
    'missing exact request records':'empty_request_records',
    'quote records must remain in receive-time and sequence order':'quote_order_not_strict',
}
for _field, _minimum in [('download metadata start',1),('download metadata end',1),('ts_recv',1),
    ('sequence',0),('bid_px_00',0),('bid_sz_00',0),('ask_px_00',0),('ask_sz_00',0)]:
    ERROR_CODES[f'{_field} must be an integer >= {_minimum}'] = _field.replace(' ','_')+'_invalid_integer'


def error_code(exc: Exception) -> str:
    # Never return arbitrary exception messages, causes, URLs, headers, or bodies.
    return ERROR_CODES.get(str(exc),'unclassified_validation_exception') if type(exc) is ValueError else 'unclassified_validation_exception'


def scalar(value) -> dict:
    if value is None:
        return {'kind':'null'}
    if isinstance(value,bool):
        return {'kind':'boolean','value':value}
    try:
        return {'kind':'integer','value':operator.index(value)}
    except TypeError:
        pass
    if isinstance(value,str):
        if value in SAFE_TEXT:
            return {'kind':'text','value':value}
        return {'kind':'other_text','sha256':hashlib.sha256(value.encode()).hexdigest(),'length':len(value)}
    if isinstance(value,bytes):
        return {'kind':'bytes','sha256':hashlib.sha256(value).hexdigest(),'length':len(value)}
    return {'kind':'other_type'}


def inspect_store(store, r: dict) -> tuple[dict,list[dict]]:
    quote.require_exact(r,request(),'diagnostic request')
    result = {'normalization_passed':False,'normalization_code':None,
              'normalized_content_sha256':None,'normalized_row_count':None,
              'metadata':{},'frame':{},'runtime_input_eligible':False}
    try:
        records = parent.normalize(store,r)
        result.update(normalization_passed=True,normalization_code='passed',
            normalized_content_sha256=quote.canonical_fingerprint(records),normalized_row_count=len(records))
    except Exception as exc:
        result['normalization_code'] = error_code(exc)
    metadata = getattr(store,'metadata',None)
    for name in ('dataset','schema','stype_in'):
        result['metadata'][name] = scalar(_metadata_value(metadata,name))
    symbols = _metadata_field(metadata,'symbols')
    result['metadata']['symbols_match'] = isinstance(symbols,(tuple,list)) and list(symbols)==r['symbols']
    for name in ('start','end'):
        try:
            result['metadata'][name] = {'raw':scalar(_metadata_field(metadata,name)),
                'interpreted_ns':_metadata_timestamp_ns(metadata,name),'expected_ns':r[name+'_ns']}
        except Exception as exc:
            result['metadata'][name] = {'code':error_code(exc),'expected_ns':r[name+'_ns']}
    projection = []
    try:
        frame = _mapped_frame(store)
        if len(frame) > MAX_ROWS:
            raise ValueError('diagnostic row ceiling exceeded')
        available = [name for name in FIELDS if name in frame.columns]
        result['frame'] = {'mapping_passed':True,'row_count':len(frame),'projected_fields':available,
            'missing_required_fields':[n for n in FIELDS[:7] if n not in available]}
        for index, row in enumerate(frame[available].itertuples(index=False,name=None)):
            projection.append({'index':index,'fields':{name:scalar(value) for name,value in zip(available,row,strict=True)}})
    except Exception as exc:
        result['frame'] = {'mapping_passed':False,'code':'row_ceiling_exceeded' if type(exc) is ValueError and str(exc)=='diagnostic row ceiling exceeded' else error_code(exc)}
    # This second unchanged layer pinpoints order-only failures without treating
    # the unvalidated projection as an eligible input tape.
    try:
        normalized = _normalize_store(store,r)
        result['normalizer_layer_passed'] = True
        result['normalized_row_count'] = len(normalized)
        result['normalized_content_sha256'] = quote.canonical_fingerprint(normalized)
        previous = None
        first = None
        count = 0
        for index, row in enumerate(normalized):
            key = (row['ts_recv_ns'],row['sequence'],row['symbol'])
            if previous is not None and key <= previous:
                count += 1
                if first is None:
                    first = {'row_index':index,'previous_key':list(previous),'current_key':list(key),
                             'equal_key':key==previous}
            previous = key
        result['order_observation'] = {'non_strict_adjacent_count':count,'first':first}
    except Exception as exc:
        result['normalizer_layer_passed'] = False
        result['normalizer_layer_code'] = error_code(exc)
    result['projection_content_sha256'] = quote.canonical_fingerprint(projection)
    result['projection_row_count'] = len(projection)
    return seal(result), projection


def write_projection(path: Path, rows: list[dict]) -> dict:
    if len(rows) > MAX_ROWS:
        raise ValueError('diagnostic projection row ceiling exceeded')
    digest = hashlib.sha256()
    count = 0
    with path.open('xb') as raw:
        with gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as stream:
            for row in rows:
                data = (json.dumps(row,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
                count += len(data)
                if count > MAX_PROJECTION_BYTES:
                    raise ValueError('diagnostic projection byte ceiling exceeded')
                digest.update(data); stream.write(data)
    if path.stat().st_size > MAX_RETAINED_PROJECTION_BYTES:
        raise ValueError('diagnostic retained byte ceiling exceeded')
    return {'row_count':len(rows),'uncompressed_bytes':count,'uncompressed_sha256':digest.hexdigest(),
            'file_bytes':path.stat().st_size,'file_sha256':file_sha(path),'runtime_input_eligible':False}
