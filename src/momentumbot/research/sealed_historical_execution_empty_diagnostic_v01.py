"""One-request diagnostic of the immutable historical v0.2 empty-input failure.

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

from momentumbot.research import sealed_historical_execution_acquisition_v02 as parent
from momentumbot.research import sealed_historical_execution_quote_v01 as quote
from momentumbot.research.prospective_market_input_acquisition import (
    _mapped_frame, _metadata_field, _metadata_timestamp_ns, _metadata_value,
    _normalize_store,
)

CONTRACT_ID = 'sealed-historical-execution-input-empty-diagnostic-v0.1'
CONTRACT_PATH = f'research/strategy/{CONTRACT_ID}.json'
EXECUTION_PATH = f'research/strategy/{CONTRACT_ID}-execution.json'
WORKFLOW_PATH = '.github/workflows/sealed-historical-execution-input-empty-diagnostic-v01.yml'
CONSUMPTION_REF = f'refs/tags/{CONTRACT_ID}-consumed'
FAILURE_RUN_ID = 34076412463
FAILURE_ARTIFACT_ID = 10002303908
FAILURE_ZIP_SHA = '2065c140c2c14bc7da14a22483934eb1631169a36a599e522e0b59c27d7ff6e9'
FAILURE_REPORT_PATH = 'research/data-audits/sealed-historical-execution-input-acquisition-v0.2-report-34076412463.json'
FAILURE_REPORT_FILE_SHA = 'ddd6160e67f09420ff914c5db50b418fd60ec0fae615dfc32168eed87a69dd57'
FAILURE_REPORT_SHA = '62e20bfc72efe69c56811b49d320195da1e562f7195d2b04119e47c9284e9d6b'
FAILURE_AUDIT_PATH = 'research/data-audits/sealed-historical-execution-input-acquisition-v0.2-independent-verification-34076412463.json'
FAILURE_AUDIT_FILE_SHA = '7a6de451d21f35a31d3ccaaf0231a0173183789ce76ca12b83a6e828eff9a373'
FAILURE_AUDIT_SHA = '865695c78f182cb8699cd33a54093eea50b4b0540857997f8daaaa05138dead2'
REQUEST_SHA = '5e0ef1993dac42f58332997b14179cc1097ec37fc51f1cdcb703f9617a505d6b'
PRIOR_DBN_SHA = 'ae2ff3b0dd1be78d948ac39bda9de49eafef668e1678f92128aff6f1b227519f'
MAX_BILLABLE_BYTES = 14_640
MAX_COST_USD = '0.000016361475'
MAX_WIRE_BYTES = MAX_BILLABLE_BYTES + 65536
MAX_ROWS = 50_000
MAX_PROJECTION_BYTES = 64_000_000
MAX_RETAINED_PROJECTION_BYTES = 16_000_000
FROZEN_CODE = {'.github/workflows/sealed-historical-execution-input-acquisition-v02.yml': '94eea57c5a80a8a21cc0f2b32ea581d3cf02a3fc0661134a75b3f994dec200a0',
 'research/strategy/sealed-historical-execution-input-acquisition-v0.2-execution.json': '53a44b7a7b2e0710fa9a47eb0153c959610cc4857edbc3e803dc1b8a51f905d8',
 'scripts/acquire_sealed_historical_execution_inputs_v02.py': '33bca1b571c5e11f3d57473e80cc76e1caef52b9da8a064c5784ff665dd5870f',
 'src/momentumbot/research/prospective_market_input_acquisition.py': '5f1e354ae74512c03f78413b9e19b753ecc210083f41460468f124d1a23fcfae',
 'src/momentumbot/research/sealed_historical_execution_acquisition_v02.py': '92877530ccbea68c1842e76e2438806db935ccad9cad326a119e1cda7065628f',
 'src/momentumbot/research/sealed_historical_execution_diagnostic_transport_v01.py': 'eeff81e0327e39e5eb1adc6e3bb963c0ecc3946099167cb67d2da96eb82e9c6e',
 'src/momentumbot/research/sealed_historical_execution_diagnostic_v01.py': '98d277b97f639dbebc9922c0ff4097f4022b04f85d3c7d7ea67df4b524c1e6ea',
 'src/momentumbot/research/sealed_historical_record_order_v01.py': '407e02fc6fe908e26715fac2799f0debf356e96336b640e795b50287762dec6b'}
FIELDS = ('symbol','ts_recv','sequence','bid_px_00','bid_sz_00','ask_px_00','ask_sz_00',
          'ts_event','instrument_id','publisher_id','flags','action','side','depth')
SAFE_TEXT = frozenset({'JVA','XNAS.ITCH','xnas.itch','mbp-1','status','raw_symbol',
    'raw-symbol','instrument_id','instrument-id','A','C','M','R','T','F','N','B','S','Y','~'})
seal, write_json, file_sha, frozen = quote.seal, quote.write_json, quote.file_sha, quote.frozen
IMMUTABLE_REFS = {**parent.IMMUTABLE_REFS,
    'tags/sealed-historical-execution-input-acquisition-v0.2-consumed':'e2c250367895d209ec4706288a22655636298685'}


def request() -> dict:
    return {'dataset':'XNAS.ITCH','schema':'mbp-1','symbols':['JVA'],'stype_in':'raw_symbol',
            'trading_date':'2025-06-13','request_id':'2025-06-13-JVA-mbp-1',
            'start_ns':1749822929742083339,'end_ns':1749822930392083340,'end_exclusive':True}


def contract() -> dict:
    return seal({'schema_version':1,'contract_id':CONTRACT_ID,
        'artifact_type':'registered_single_request_empty_input_diagnostic',
        'parent_commit_sha':'36375ab2d627e98b864aba3c91157efe55e2203c',
        'parent_tree_sha':'764c0a1880f0d4ec32120b27af04bb2fd146368a',
        'failure_run_id':FAILURE_RUN_ID,'failure_run_attempt':1,'failure_artifact_id':FAILURE_ARTIFACT_ID,
        'failure_zip_sha256':FAILURE_ZIP_SHA,'failure_report_content_sha256':FAILURE_REPORT_SHA,
        'failure_report_file_sha256':FAILURE_REPORT_FILE_SHA,'failure_audit_content_sha256':FAILURE_AUDIT_SHA,
        'failure_audit_file_sha256':FAILURE_AUDIT_FILE_SHA,'prior_ephemeral_dbn_sha256':PRIOR_DBN_SHA,
        'request':request(),'request_content_sha256':REQUEST_SHA,'request_count':1,
        'original_request_list_content_sha256':quote.REQUEST_LIST_SHA256,
        'parent_quote_report_content_sha256':parent.parent.QUOTE_REPORT_CONTENT_SHA,
        'maximum_metadata_calls':2,'maximum_timeseries_calls':1,'maximum_http_attempts':3,
        'maximum_billable_bytes':MAX_BILLABLE_BYTES,'maximum_quoted_cost_usd':MAX_COST_USD,
        'immutable_refs':IMMUTABLE_REFS,'request_index':24,
        'hypothesis':'positive_sub_ten_minute_metadata_estimate_can_accompany_metadata_only_exact_DBN',
        'native_observation':'bounded_complete_DBN_decoder_before_dataframe_mapping_no_rewrite',
        'maximum_decompressed_dbn_bytes':MAX_PROJECTION_BYTES,
        'maximum_wire_bytes':MAX_WIRE_BYTES,'maximum_projection_rows':MAX_ROWS,
        'maximum_projection_bytes':MAX_PROJECTION_BYTES,
        'maximum_retained_projection_bytes':MAX_RETAINED_PROJECTION_BYTES,
        'preflight':'both_fresh_exact_nonzero_size_and_cost_at_or_below_original_failed_request_ceilings',
        'frozen_code_file_sha256':FROZEN_CODE,'normalization':'execute_frozen_v02_record_order_normalize_once',
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
        'next_gate':'independent_exact_empty_input_diagnosis_then_registered_missing_input_resolution'})


def validate_inputs(root: Path) -> dict:
    requests, quoted = parent.validate_inputs(root)
    quote.require_exact(requests[24],request(),'exact failed request')
    if quote.canonical_fingerprint(request()) != REQUEST_SHA:
        raise ValueError('diagnostic request differs')
    first = quoted['quote_rows'][24]
    if first['billable_size_bytes'] != MAX_BILLABLE_BYTES or first['quoted_cost_usd'] != MAX_COST_USD:
        raise ValueError('original failed request quote ceilings differ')
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
    expected = frozen(root / FAILURE_AUDIT_PATH)['result_zip_verification']['files']
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if len(names)!=len(set(names)) or any(info.is_dir() or (info.external_attr >> 16) & 0o170000 == 0o120000 for info in z.infolist()):
            raise ValueError('failed acquisition archive type differs')
        if len(names) != len(expected) or set(names) != set(expected):
            raise ValueError('failed acquisition archive members differ')
        for name in names:
            raw = z.read(name)
            if {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()} != expected[name]:
                raise ValueError('failed acquisition archive file differs')
            if name.endswith('.json'):
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
        good = 0 < values[0] <= MAX_BILLABLE_BYTES and 0 < Decimal(values[1]) <= Decimal(MAX_COST_USD)
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
    'missing exact request records':'empty_exact_request',
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
        result['normalizer_layer_row_count'] = len(normalized)
        result['normalizer_layer_content_sha256'] = quote.canonical_fingerprint(normalized)
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


def metadata_observation(metadata) -> dict:
    """Retain bounded symbology evidence without arbitrary provider text."""
    r = request()
    exact = (_metadata_value(metadata, 'dataset') == 'xnas.itch'
        and _metadata_value(metadata, 'schema') == 'mbp-1'
        and _metadata_value(metadata, 'stype_in') == 'raw-symbol'
        and _metadata_value(metadata, 'stype_out') == 'instrument-id'
        and list(_metadata_field(metadata, 'symbols') or ()) == r['symbols']
        and _metadata_timestamp_ns(metadata, 'start') == r['start_ns']
        and _metadata_timestamp_ns(metadata, 'end') == r['end_ns'])
    result = {'exact_request_metadata': exact, 'mappings': []}
    for name in ('dataset', 'schema', 'stype_in', 'stype_out', 'start', 'end', 'limit', 'version', 'ts_out'):
        result[name] = scalar(_metadata_field(metadata, name))
    for name in ('symbols', 'partial', 'not_found'):
        values = _metadata_field(metadata, name)
        if not isinstance(values, (list, tuple)) or len(values) > MAX_ROWS:
            raise ValueError('invalid bounded metadata list')
        result[name] = [scalar(value) for value in values]
    mappings = _metadata_field(metadata, 'mappings')
    if not isinstance(mappings, dict) or len(mappings) > MAX_ROWS:
        raise ValueError('invalid bounded metadata mappings')
    count = 0
    for symbol, intervals in mappings.items():
        if not isinstance(intervals, list):
            raise ValueError('invalid bounded metadata intervals')
        projected = []
        for row in intervals:
            count += 1
            if count > MAX_ROWS or set(row) != {'start_date', 'end_date', 'symbol'}:
                raise ValueError('invalid bounded metadata interval')
            # Dates and numeric instrument identifiers are typed; all other text is hashed.
            from datetime import date
            dates = {}
            for name in ('start_date', 'end_date'):
                value = row[name]
                dates[name] = value.isoformat() if type(value) is date else scalar(value)
            value = row['symbol']
            instrument = int(value) if isinstance(value, str) and re.fullmatch('[0-9]{1,10}', value) else None
            projected.append({**dates, 'instrument_id': instrument, 'symbol': scalar(value)})
        result['mappings'].append({'raw_symbol': scalar(symbol), 'intervals': projected})
    result['mapping_interval_count'] = count
    result['decoded_metadata_encoded_sha256'] = hashlib.sha256(metadata.encode()).hexdigest()
    return result


def inspect_native_dbn(path: Path) -> tuple[dict, list[dict]]:
    """Count every native record before any DataFrame conversion or symbol mapping.

    The pinned decoder must exhaust a complete bounded stream. A truncated final
    record is a diagnostic failure, never evidence of an empty request.
    """
    import databento_dbn as dbn
    import zstandard
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_WIRE_BYTES:
        raise ValueError('missing or oversized native DBN')
    wire = path.read_bytes()
    if wire[:4] == b'\x28\xb5\x2f\xfd':
        size = zstandard.frame_content_size(wire)
        if size not in (zstandard.CONTENTSIZE_UNKNOWN,zstandard.CONTENTSIZE_ERROR) and size > MAX_PROJECTION_BYTES:
            raise ValueError('native decompression ceiling exceeded')
        # Require a complete frame and reject trailing/concatenated payloads.
        raw = zstandard.ZstdDecompressor().decompress(wire,max_output_size=MAX_PROJECTION_BYTES,allow_extra_data=False)
        compression = 'zstd'
    else:
        raw, compression = wire, 'none'
    if len(raw) > MAX_PROJECTION_BYTES:
        raise ValueError('native decompression ceiling exceeded')
    decoder = dbn.DBNDecoder(upgrade_policy=dbn.VersionUpgradePolicy.UPGRADE_TO_V3)
    records = decoder.write_and_decode(raw)
    records.extend(decoder.decode())
    if decoder.buffer():
        raise ValueError('incomplete native DBN record')
    metadata = [row for row in records if isinstance(row, dbn.Metadata)]
    if len(metadata) != 1 or len(records) - 1 > MAX_ROWS:
        raise ValueError('native metadata or record count differs')
    result = {'decoding_complete': True, 'compression': compression,
        'wire_bytes': len(wire), 'wire_sha256': hashlib.sha256(wire).hexdigest(),
        'decompressed_bytes': len(raw), 'decompressed_sha256': hashlib.sha256(raw).hexdigest(),
        'metadata': metadata_observation(metadata[0]), 'native_record_count': len(records)-1,
        'record_types': {}, 'runtime_input_eligible': False}
    digest, rows = hashlib.sha256(), []
    for record in records:
        if isinstance(record, dbn.Metadata):
            continue
        digest.update(bytes(record))
        name = type(record).__name__
        if name not in {'MBP1Msg', 'SymbolMappingMsg', 'ErrorMsg', 'SystemMsg'}:
            name = 'other_record_type'
        result['record_types'][name] = result['record_types'].get(name, 0) + 1
        if isinstance(record, dbn.MBP1Msg):
            values = {name: getattr(record, name) for name in FIELDS[1:]
                if name not in {'bid_px_00', 'bid_sz_00', 'ask_px_00', 'ask_sz_00'}}
            level = record.levels[0]
            values.update(bid_px_00=level.bid_px, bid_sz_00=level.bid_sz,
                          ask_px_00=level.ask_px, ask_sz_00=level.ask_sz)
            # DBN stores these as ASCII bytes; DataFrame exposes the same characters.
            for name in ('action', 'side'):
                values[name] = chr(operator.index(values[name]))
            rows.append({'index': len(rows), 'fields': {name: scalar(values[name]) for name in FIELDS[1:]}})
    result.update(native_mbp1_count=len(rows), decoded_v3_record_bytes_sha256=digest.hexdigest(),
                  projection_content_sha256=quote.canonical_fingerprint(rows))
    return seal(result), rows


def observation_outcome(native: dict, mapped: dict, native_rows: list[dict], mapped_rows: list[dict]) -> dict:
    """Evidence classification never grants acquisition or runtime eligibility."""
    same = len(native_rows) == len(mapped_rows) and all(
        all(row['fields'].get(name) == other['fields'].get(name) for name in FIELDS[1:])
        for row, other in zip(native_rows, mapped_rows, strict=True))
    complete = (native['decoding_complete'] is True and native['metadata']['exact_request_metadata'] is True
        and mapped['frame'].get('mapping_passed') is True and same
        and mapped.get('normalizer_layer_passed') is True
        and mapped.get('normalizer_layer_row_count') == native['native_mbp1_count'])
    if native['native_mbp1_count']==0 and (mapped['normalization_passed'] is not False
        or mapped['normalization_code']!='empty_exact_request'):
        complete = False
    if not complete:
        code = 'native_mapped_evidence_inconsistent_or_unavailable'
    elif native['native_record_count'] == 0 and mapped['normalization_code'] == 'empty_exact_request':
        code = 'metadata_only_exact_dbn_empty_before_mapping'
    elif native['native_mbp1_count'] == 0:
        code = 'no_native_mbp1_records'
    elif mapped['normalization_passed'] is True:
        code = 'nonempty_exact_dbn_normalization_passed_diagnostic_only'
    else:
        code = 'nonempty_native_records_normalization_rejected'
    return seal({'diagnostic_evidence_complete': complete, 'code': code,
        'native_mapped_fields_identical': same, 'native_mbp1_count': native['native_mbp1_count'],
        'mapped_row_count': mapped.get('frame', {}).get('row_count'),
        'normalization_code': mapped['normalization_code'], 'runtime_input_eligible': False,
        'acquisition_gate_passed': False})


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


def verify_result(output: Path, root: Path) -> dict:
    """Recompute the complete retained diagnostic, including empty projections."""
    validate_inputs(root)
    inventory = frozen(output/'diagnostic-inventory.json')
    actual = {}
    for path in sorted(output.rglob('*')):
        if path.is_symlink() or not path.is_file():
            raise ValueError('diagnostic inventory contains non-files')
        name = path.relative_to(output).as_posix()
        if name == 'diagnostic-inventory.json':
            continue
        actual[name] = {'sha256':file_sha(path),'bytes':path.stat().st_size}
        if name.endswith('.json'):
            frozen(path)
    quote.require_exact(actual,inventory['files'],'complete diagnostic inventory')
    expected = {'contract.json','execution.json','parent-failure-audit.json','parent-failure-report.json',
        'parent-quote-report.json','consumption.json','environment.json','request.json','requote-report.json',
        'native-observation.json','native-projection.jsonl.gz','normalization-observation.json',
        'diagnostic-projection.jsonl.gz','diagnostic-receipt.json','http-ledger.json','diagnostic-report.json'}
    if set(actual) != expected:
        raise ValueError('complete diagnostic archive members differ')
    for repo_path,name in ((CONTRACT_PATH,'contract.json'),(EXECUTION_PATH,'execution.json'),
        (FAILURE_AUDIT_PATH,'parent-failure-audit.json'),(FAILURE_REPORT_PATH,'parent-failure-report.json'),
        (parent.parent.QUOTE_REPORT_PATH,'parent-quote-report.json')):
        if (root/repo_path).read_bytes() != (output/name).read_bytes():
            raise ValueError('diagnostic frozen source differs')
    report, ledger, receipt = (frozen(output/name) for name in
        ('diagnostic-report.json','http-ledger.json','diagnostic-receipt.json'))
    native, mapped = (frozen(output/name) for name in ('native-observation.json','normalization-observation.json'))
    expected_metadata = {'dataset':scalar('XNAS.ITCH'),'schema':scalar(1),'stype_in':scalar(1),
        'stype_out':scalar(0),'symbols':[scalar('JVA')],'start':scalar(request()['start_ns']),
        'end':scalar(request()['end_ns'])}
    quote.require_exact({k:native['metadata'].get(k) for k in expected_metadata},expected_metadata,
        'native exact metadata fields')
    if (native['runtime_input_eligible'] is not False or mapped['runtime_input_eligible'] is not False
        or not 0<native['decompressed_bytes']<=MAX_PROJECTION_BYTES
        or native['compression'] not in {'zstd','none'}):
        raise ValueError('native diagnostic evidence boundary differs')
    execution, marker = frozen(output/'execution.json'), frozen(output/'consumption.json')
    expected_marker = consumption(execution,{'GITHUB_SHA':report['provenance']['execution_commit_sha'],
        'GITHUB_RUN_ID':report['provenance']['workflow_run_id']})
    quote.require_exact(marker,expected_marker,'diagnostic consumption provenance')
    quote.require_exact(report['provenance'],{
        'execution_commit_sha':marker['execution_commit_sha'],'workflow_run_id':marker['workflow_run_id'],
        'workflow_run_attempt':1,'code_commit_sha':execution['code_commit_sha'],'code_tree_sha':execution['code_tree_sha'],
        'execution_content_sha256':execution['content_sha256'],'consumption_content_sha256':marker['content_sha256']},
        'diagnostic exact provenance')
    pins = dict(re.findall(r'^([A-Za-z0-9_.-]+)==([^\s\\]+)',(root/quote.LOCK_PATH).read_text(),re.M))
    quote.require_exact(frozen(output/'environment.json'),seal({'implementation':'CPython','python_version':'3.12.14',
        'requirements_sha256':quote.LOCK_SHA256,'package_versions':pins}),'diagnostic pinned environment')
    quote.require_exact(frozen(output/'request.json'),seal({'request':request(),'request_content_sha256':REQUEST_SHA}),
        'diagnostic exact request')
    if any(report.get(k) is not False for k in ('runtime_input_eligible','acquisition_gate_passed',
        'account_or_fill_simulation_executed','backtesting_executed','retrospective_inputs_loaded',
        'policy_changed','consumed_parent_rerun','raw_dbn_retained')):
        raise ValueError('diagnostic authority boundary differs')
    if report['error'] is not None or report['raw_temp_directory_removed'] is not True:
        raise ValueError('diagnostic failure or incomplete cleanup')
    if (ledger['contract_id']!=CONTRACT_ID or ledger['http_attempts']!=3 or ledger['blocked_attempts']!=0
        or any(ledger[k]!=0 for k in ('automatic_retries','redirects_followed','unregistered_endpoint_calls'))):
        raise ValueError('diagnostic exact ledger differs')
    if report['http_attempts']!=3 or report['blocked_attempts']!=0:
        raise ValueError('diagnostic report ledger differs')
    attempts = ledger['attempts']
    if len(attempts)!=3:
        raise ValueError('diagnostic attempt count differs')
    for i,(row,method) in enumerate(zip(attempts,('metadata.get_billable_size','metadata.get_cost','timeseries.get_range'),strict=True)):
        if (row['ordinal']!=i+1 or row['method']!=method or row['request_content_sha256']!=REQUEST_SHA
            or row['http_status']!=200 or row['status']!=('success' if i<2 else 'complete')
            or row['maximum_wire_bytes']!=(65536 if i<2 else MAX_WIRE_BYTES)
            or not 0<row['wire_bytes']<=row['maximum_wire_bytes']):
            raise ValueError('diagnostic HTTP attempt differs')
    expected_requote = preflight(ledger['metadata_calls'],2,0)
    if not expected_requote['preflight_passed']:
        raise ValueError('diagnostic quote gate failed')
    quote.require_exact(frozen(output/'requote-report.json'),expected_requote,'fresh exact diagnostic quote')
    quote.require_exact(report['requote'],expected_requote,'report quote')
    rows_by_name = {}
    for name, field in (('native-projection.jsonl.gz','native_projection'),('diagnostic-projection.jsonl.gz','projection')):
        rows, digest, count = [],hashlib.sha256(),0
        with gzip.open(output/name,'rb') as stream:
            for line in stream:
                count += len(line)
                if count>MAX_PROJECTION_BYTES or len(rows)>=MAX_ROWS:
                    raise ValueError('diagnostic projection exceeds bounds')
                row = json.loads(line)
                canonical = (json.dumps(row,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
                if canonical != line or set(row)!={'index','fields'} or row['index']!=len(rows):
                    raise ValueError('diagnostic projection canonical order differs')
                fields = FIELDS[1:] if field=='native_projection' else FIELDS
                if set(row['fields'])!=set(fields):
                    raise ValueError('diagnostic typed projection fields differ')
                digest.update(line);rows.append(row)
        stats = {'row_count':len(rows),'uncompressed_bytes':count,'uncompressed_sha256':digest.hexdigest(),
            'file_bytes':(output/name).stat().st_size,'file_sha256':file_sha(output/name),'runtime_input_eligible':False}
        if stats['file_bytes']>MAX_RETAINED_PROJECTION_BYTES:
            raise ValueError('diagnostic projection retention differs')
        quote.require_exact(report[field],stats,'full decompressed diagnostic projection')
        quote.require_exact(receipt[field],stats,'receipt projection')
        rows_by_name[field]=rows
    if (native['native_mbp1_count']!=len(rows_by_name['native_projection'])
        or native['native_record_count']!=sum(native['record_types'].values())
        or native['record_types'].get('MBP1Msg',0)!=native['native_mbp1_count']
        or native['projection_content_sha256']!=quote.canonical_fingerprint(rows_by_name['native_projection'])
        or mapped['projection_content_sha256']!=quote.canonical_fingerprint(rows_by_name['projection'])
        or mapped['projection_row_count']!=len(rows_by_name['projection'])):
        raise ValueError('native or mapped projection commitment differs')
    if native['native_record_count']==0 and native['decoded_v3_record_bytes_sha256']!=hashlib.sha256(b'').hexdigest():
        raise ValueError('metadata-only DBN has nonempty record commitment')
    expected_outcome = observation_outcome(native,mapped,rows_by_name['native_projection'],rows_by_name['projection'])
    quote.require_exact(report['outcome'],expected_outcome,'native and mapped outcome')
    quote.require_exact(report['native_observation'],native,'report native observation')
    quote.require_exact(report['observation'],mapped,'report mapped observation')
    quote.require_exact(receipt,seal({'request':request(),'request_content_sha256':REQUEST_SHA,
        'ephemeral_dbn_sha256':native['wire_sha256'],'observation_content_sha256':mapped['content_sha256'],
        'native_observation_content_sha256':native['content_sha256'],'native_projection':report['native_projection'],
        'projection':report['projection'],'runtime_input_eligible':False}),'diagnostic receipt')
    if (not expected_outcome['diagnostic_evidence_complete'] or not report['diagnostic_evidence_complete']
        or not inventory['diagnostic_evidence_complete'] or inventory['runtime_input_eligible'] is not False
        or report['contract_id']!=CONTRACT_ID or report['contract_content_sha256']!=contract()['content_sha256']
        or report['request_content_sha256']!=REQUEST_SHA or report['failure_zip_sha256']!=FAILURE_ZIP_SHA
        or report['next_gate']!=contract()['next_gate']
        or native['wire_sha256']!=report['ephemeral_dbn_sha256'] or native['wire_sha256']!=attempts[2]['dbn_file_sha256']
        or native['wire_bytes']!=attempts[2]['wire_bytes']
        or report['same_dbn_bytes_as_failed_parent']!=(native['wire_sha256']==PRIOR_DBN_SHA)):
        raise ValueError('diagnostic complete report binding differs')
    return seal({'verification_passed':True,'file_count':len(actual)+1,'report_file_sha256':file_sha(output/'diagnostic-report.json'),
        'report_content_sha256':report['content_sha256'],'inventory_content_sha256':inventory['content_sha256'],
        'native_record_count':native['native_record_count'],'mapped_row_count':len(rows_by_name['projection']),
        'outcome':expected_outcome['code'],'http_attempts':3,'blocked_attempts':0,'acquisition_gate_passed':False})
