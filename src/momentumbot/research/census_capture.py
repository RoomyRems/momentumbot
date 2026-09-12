"""Bounded census collector and independent raw replay using the frozen order repair."""
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import stat
import time
import zipfile

from momentumbot.research import census_order_repair as protocol

legacy, diagnostic = protocol.legacy, protocol.diagnostic
require, exact, seal, sha = legacy.require, legacy.exact, legacy.seal, legacy.sha
render, parse_json = legacy.render, legacy.parse_json
ID = 'early-pullback-census-repaired-v0.3'
DETAILS = diagnostic.SAFE_ERRORS | {'cross-page ordering regression', 'duplicate membership identity',
    'repeated cursor', 'census page ceiling exceeded', 'empty complete census is unavailable, not a no-opportunity day',
    'provider order witness differs', 'provider/canonical ticker population differs'}


def inventory(store):
    return seal({'contract_id': ID, 'files': store.inventory()['files']})


def report(state, attempts, failure):
    return seal({'contract_id': ID, 'artifact_type': 'unattributed_repaired_census_capture',
        'protocol_complete': state.next_request() is None and failure is None,
        'attempt_count': attempts, 'failure': failure, 'dates': state.summary(),
        'current_type_dictionary_captured': state.types is not None,
        'current_taxonomy_is_historical_identity_proof': False, **legacy.BOUNDARY})


def detail(error):
    return str(error) if str(error) in DETAILS else 'validation_rejected'


class CaptureSession:
    def __init__(self, contract, *, output, transport, credential, clock_ns=time.monotonic_ns,
            sleeper=time.sleep, utc_now=lambda: datetime.now(timezone.utc).isoformat(), progress=lambda _: None):
        require(callable(transport), 'explicit transport required')
        require(type(credential) is str and 8 <= len(credential) <= 1024 and credential.isascii()
            and all(32 < ord(c) < 127 for c in credential), 'bounded credential format required')
        diagnostic.base.verify_seal(contract)
        require(contract.get('contract_id') == ID, 'repaired capture contract required')
        exact(contract.get('limits'), legacy.limits(), 'registered limits differ')
        self.store = legacy.RetainedFiles(output)
        self.store.write('contract.json', render(contract))
        self.contract, self.transport, self.credential = contract, transport, credential
        self.clock_ns, self.sleeper, self.utc_now, self.progress = clock_ns, sleeper, utc_now, progress
        self.state, self.attempts, self.finished, self.last_start = protocol.CensusState(), 0, False, None

    def _once(self, request):
        require(self.attempts < legacy.MAX_ATTEMPTS, 'HTTP attempt ceiling exceeded')
        legacy.validate_request(request)
        if self.last_start is not None:
            remaining = self.last_start + legacy.INTERVAL_NS - self.clock_ns()
            if remaining > 0:
                self.sleeper(remaining / 1_000_000_000)
        started = self.clock_ns()
        require(type(started) is int and started >= 0 and
            (self.last_start is None or started - self.last_start >= legacy.INTERVAL_NS), 'request pacing failed')
        ordinal = self.attempts
        prefix = f'{ordinal:04d}'
        intent = seal({'contract_id': ID, 'ordinal': ordinal, 'request': request,
            'started_at': self.utc_now(), 'started_monotonic_ns': started})
        self.store.write(prefix + '.intent.json', render(intent))
        self.last_start, self.attempts = started, self.attempts + 1
        raw = status = normalized = error = explanation = None
        complete = retained = projected = False
        try:
            reply = self.transport(request, self.credential)
            require(type(reply) is dict and set(reply) == {'status', 'body', 'complete', 'encoding'}, 'transport reply shape')
            status, raw, complete = reply['status'], reply['body'], reply['complete']
            require(type(status) is int and 100 <= status <= 599 and type(raw) is bytes
                and len(raw) <= legacy.MAX_BODY + 1 and type(complete) is bool, 'invalid transport observation')
            if len(raw) > legacy.MAX_BODY:
                error = 'response_too_large'
            elif not complete:
                error = 'incomplete_body'
            elif reply['encoding'] not in ('', 'identity'):
                error = 'content_encoding'
            elif status != 200:
                error = 'http_error'
            else:
                safe, error = diagnostic.safe_to_retain(raw, self.credential)
                if safe:
                    if self.store.payload_bytes + len(raw) > legacy.MAX_PAYLOAD:
                        error = 'retention_limit'
                    else:
                        # Persist safe originals before parsing, including rejected payloads.
                        self.store.write(prefix + '.body.json', raw, payload=True)
                        retained = True
                        try:
                            normalized = protocol.project_body(request, raw)
                        except (ValueError, TypeError, KeyError, UnicodeError, RuntimeError) as exc:
                            error, explanation = 'invalid_payload', detail(exc)
                        if error is None:
                            normalized_raw = render(normalized)
                            if self.store.payload_bytes + len(normalized_raw) > legacy.MAX_PAYLOAD:
                                error = 'retention_limit'
                            else:
                                self.store.write(prefix + '.normalized.json', normalized_raw, payload=True)
                                projected = True
                                try:
                                    self.state.accept(request, sha(raw), normalized)
                                except (ValueError, TypeError, KeyError, RuntimeError) as exc:
                                    error, explanation = 'invalid_census_chain', detail(exc)
        except Exception:
            error, explanation, complete = 'transport_or_retention_error', None, False
            if type(raw) is not bytes or len(raw) > legacy.MAX_BODY + 1: raw = None
            if type(status) is not int or not 100 <= status <= 599: status = None
        receipt = seal({'contract_id': ID, 'ordinal': ordinal, 'intent_sha256': intent['content_sha256'],
            'request_sha256': request['content_sha256'], 'finished_at': self.utc_now(),
            'status': status, 'body_complete': complete, 'body_bytes': None if raw is None else len(raw),
            'body_sha256': None if raw is None else sha(raw), 'body_retained': retained,
            'normalized_retained': projected, 'normalized_sha256': legacy.fingerprint(normalized) if projected else None,
            'error': error, 'detail': explanation})
        self.store.write(prefix + '.receipt.json', render(receipt))
        self.progress({'attempts': self.attempts, 'date': request.get('trading_date'),
            'page': request.get('page'), 'status': status, 'error': error,
            'dates_exhausted': len(self.state.exhausted)})
        return error, explanation

    def run(self):
        require(not self.finished and self.attempts == 0, 'capture cannot restart or resume')
        failure = None
        try:
            while (request := self.state.next_request()) is not None:
                error, explanation = self._once(request)
                if error:
                    failure = {'ordinal': self.attempts - 1, 'reason': error, 'detail': explanation}
                    break
        except BaseException:
            failure = {'ordinal': self.attempts - 1 if self.attempts else None, 'reason': 'interrupted', 'detail': None}
            raise
        finally:
            self.finished = True
            result = report(self.state, self.attempts, failure)
            self.store.write('report.json', render(result))
            self.store.write('inventory.json', render(inventory(self.store)))
        return result


def verify_archive(path, *, expected_bytes, expected_sha256, expected_inventory_sha256, contract):
    """Reparse every original response; outer and inventory pins must be independent."""
    path = Path(path)
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents))
        and type(expected_bytes) is int and 0 < expected_bytes <= legacy.MAX_TOTAL
        and path.stat().st_size == expected_bytes, 'archive size/path differs')
    for value in (expected_sha256, expected_inventory_sha256): diagnostic.base.hash_value(value)
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1_048_576), b''): digest.update(chunk)
    require(digest.hexdigest() == expected_sha256, 'external archive hash differs')
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [i.filename for i in infos]
        require(len(names) == len(set(names)) and 3 <= len(names) <= 4 * legacy.MAX_ATTEMPTS + 3,
            'archive member population differs')
        payload_bytes = sum(i.file_size for i in infos if i.filename.endswith(('.body.json', '.normalized.json')))
        require(payload_bytes <= legacy.MAX_PAYLOAD and
            sum(i.file_size for i in infos) - payload_bytes <= legacy.METADATA_RESERVE, 'archive retention ceiling')
        for item in infos:
            require(re.fullmatch(r'(?:contract|report|inventory)\.json|[0-9]{4}\.(?:intent|receipt|body|normalized)\.json', item.filename)
                and not item.is_dir() and stat.S_IFMT(item.external_attr >> 16) in (0, stat.S_IFREG)
                and item.file_size <= (legacy.MAX_BODY if item.filename.endswith('.body.json') else
                    legacy.MAX_PAYLOAD if item.filename.endswith('.normalized.json') else legacy.METADATA_RESERVE),
                'unsafe or oversized archive member')
        raw_inventory = archive.read('inventory.json')
        require(sha(raw_inventory) == expected_inventory_sha256, 'independent inventory hash differs')
        saved = parse_json(raw_inventory)
        diagnostic.base.verify_seal(saved)
        require(set(saved) == {'contract_id', 'files', 'content_sha256'} and saved['contract_id'] == ID
            and set(saved['files']) == set(names) - {'inventory.json'}, 'inventory population differs')
        for name, spec in saved['files'].items():
            raw = archive.read(name)
            exact(spec, {'bytes': len(raw), 'sha256': sha(raw)}, 'member byte commitment differs')
        exact(parse_json(archive.read('contract.json')), contract, 'independent contract differs')
        state, count, previous_ns = protocol.CensusState(), 0, None
        expected_names = {'contract.json', 'report.json', 'inventory.json'}
        while (request := state.next_request()) is not None:
            require(count < legacy.MAX_ATTEMPTS, 'archive attempt ceiling')
            prefix = f'{count:04d}'
            required = {prefix + '.' + suffix + '.json' for suffix in ('intent', 'receipt', 'body', 'normalized')}
            require(required <= set(names), 'complete page evidence missing')
            expected_names.update(required)
            intent, receipt = (parse_json(archive.read(prefix + '.' + suffix + '.json')) for suffix in ('intent', 'receipt'))
            for doc in (intent, receipt): diagnostic.base.verify_seal(doc)
            started_ns = intent.get('started_monotonic_ns')
            require(type(started_ns) is int and started_ns >= 0
                and (previous_ns is None or started_ns - previous_ns >= legacy.INTERVAL_NS), 'capture pacing differs')
            previous_ns = started_ns
            started_at, finished_at = datetime.fromisoformat(intent['started_at']), datetime.fromisoformat(receipt['finished_at'])
            require(started_at.tzinfo is not None and finished_at.tzinfo is not None and finished_at >= started_at, 'invalid capture clock')
            exact(intent, seal({'contract_id': ID, 'ordinal': count, 'request': request,
                'started_at': intent['started_at'], 'started_monotonic_ns': started_ns}), 'intent differs')
            raw = archive.read(prefix + '.body.json')
            projected = protocol.project_body(request, raw)
            require(archive.read(prefix + '.normalized.json') == render(projected), 'raw/normalized projection differs')
            exact(receipt, seal({'contract_id': ID, 'ordinal': count, 'intent_sha256': intent['content_sha256'],
                'request_sha256': request['content_sha256'], 'finished_at': receipt['finished_at'],
                'status': 200, 'body_complete': True, 'body_bytes': len(raw), 'body_sha256': sha(raw),
                'body_retained': True, 'normalized_retained': True, 'normalized_sha256': legacy.fingerprint(projected),
                'error': None, 'detail': None}), 'receipt differs')
            state.accept(request, sha(raw), projected)
            count += 1
        require(set(names) == expected_names, 'extra evidence after exhaustion')
        exact(parse_json(archive.read('report.json')), report(state, count, None), 'terminal census report differs')
    return seal({'contract_id': ID, 'archive_bytes': expected_bytes, 'archive_sha256': expected_sha256,
        'inventory_file_sha256': expected_inventory_sha256, 'attempt_count': count,
        'verified_member_count': len(names), 'protocol_complete': True, 'dates': state.summary(), **legacy.BOUNDARY})
