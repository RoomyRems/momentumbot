"""Ordering-only Alpaca repair, exact saved prefix, and bounded suffix capture.

Original action order is retained, never replaced by a fabricated chronological
sequence. Process dates remain bounded; IDs and cursors must remain unique.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import stat
import zipfile

from momentumbot.research import coverage_capture as old
from momentumbot.research import coverage_capture_hosted as parent

require, exact, seal, sha, render, parse = old.require, old.exact, old.seal, old.sha, old.render, old.parse
ID = 'early-pullback-coverage-continuation-v0.2'
PREFIX_PATH = 'research/data-audits/' + ID + '/original-prefix.zip'
PREFIX_ATTEMPTS = 47
MAX_NEW_ATTEMPTS = old.MAX_ATTEMPTS - PREFIX_ATTEMPTS
PREFIX_PIN = {'artifact_id': 10330669089, 'run_id': 34799137954,
    'code_commit': 'af48e9f7761d80684683da02c5ef5b9bcdd800d8', 'bytes': 3493487,
    'sha256': '1d7edc9a9458b290320b5cd2963d911037d3c2b8d60bd86e01ef001a6528861a',
    'inventory_sha256': 'dc05d8cf5d9e0a13b0727128eb770a356bc189a943ca102382e1f7af0f76e9c2'}
FAILURE_SEAL = '516bf3f6b9842aab30d74dad2ef5263a161303983c35f25a8d026675d6a6b1a8'


class ActionPages(old.ActionPages):
    def _accept(self, request, reply):
        if self.root['provider'] != 'alpaca':
            return super()._accept(request, reply)
        exact(request, self.request(), 'identity request differs')
        old.validate_reply(reply)
        require(reply['status'] == 200 and reply['complete'] is True and reply['encoding'] == 'identity',
            'successful identity response required')
        raw = reply['body']
        require(len(raw) <= old.daily.MAX_BODY, 'identity body ceiling')
        payload = parse(raw)
        require(set(payload) == {'corporate_actions', 'next_page_token'}
            and type(payload['corporate_actions']) is dict, 'grouped corporate actions required')
        token = old.daily._token(payload['next_page_token'])
        groups = payload['corporate_actions']
        require(set(groups) <= {t + 's' for t in old.daily.ACTION_TYPES}, 'unrequested action group')
        rows, identities, last, regressions = [], set(self.identities), dict(self.last), {}
        for kind, events in sorted(groups.items()):
            require(type(events) is list, 'action list required')
            regressions[kind] = 0
            for event in events:
                require(type(event) is dict and 'action_type' not in event, 'original action object required')
                identity, process = event.get('id'), event.get('process_date')
                require(type(identity) is str and 0 < len(identity) <= 256, 'action ID required')
                old.iso_day(process)
                require(self.root['params']['start'] <= process <= self.root['params']['end'], 'action process date outside window')
                require(identity not in identities, 'duplicate action ID')
                regressions[kind] += int(kind in last and process < last[kind])
                identities.add(identity)
                last[kind] = process
                rows.append({**event, 'action_type': kind})
        require(len(rows) <= self.root['params']['limit'], 'action row ceiling')
        require(token is None or (rows and token not in self.tokens and len(self.pages) + 1 < old.ACTION_PAGES),
            'identity cursor repeated, empty or beyond ceiling')
        witness = {'request_sha256': request['content_sha256'], 'body_sha256': sha(raw),
            'body_bytes': len(raw), 'row_count': len(rows), 'terminal': token is None,
            'provider_order_preserved': True, 'process_date_regressions': regressions}
        self.pages.append(witness)
        self.rows.extend(rows)
        self.identities, self.last = identities, last
        self.params = dict(self.root['params'])
        self.complete = token is None
        if token is not None:
            self.tokens.add(token)
            self.params['page_token'] = token
        return deepcopy(witness)


class PanelState(old.PanelState):
    def request(self):
        require(not self.failed, 'panel failed')
        if len(self.results) == len(self.tasks): return None
        if self.current is None:
            kind, day, root = self.tasks[len(self.results)]
            self.current = old.daily.DailyCoverage(day) if kind == 'daily' else ActionPages(root)
        return self.current.request()


def verify_saved_failure(root):
    parent.validate_registration(root)
    proof = parse((Path(root) / 'research/data-audits' / old.ID / 'failure-verification.json').read_bytes())
    old.d.base.verify_seal(proof)
    require(proof['content_sha256'] == FAILURE_SEAL and proof['verified_members'] == 144
        and proof['archive_sha256'] == PREFIX_PIN['sha256'] and proof['original_attempts'] == PREFIX_ATTEMPTS,
        'accepted original failure evidence differs')
    return proof


def replay_prefix(path, panel, root):
    """Pinned original bytes reuse the accepted failure proof; replay the repaired state."""
    verify_saved_failure(root)
    path = Path(path)
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents))
        and path.stat().st_size == PREFIX_PIN['bytes'], 'original prefix size/path differs')
    with path.open('rb') as handle:
        require(hashlib.file_digest(handle, 'sha256').hexdigest() == PREFIX_PIN['sha256'], 'original prefix SHA differs')
    state = PanelState(panel)
    with zipfile.ZipFile(path) as archive:
        require(len(archive.namelist()) == len(set(archive.namelist())) == 144, 'prefix member population differs')
        raw_inventory = archive.read('inventory.json')
        require(sha(raw_inventory) == PREFIX_PIN['inventory_sha256'], 'prefix inventory differs')
        inventory = parse(raw_inventory)
        require(set(inventory['files']) == set(archive.namelist()) - {'inventory.json'}, 'prefix inventory population differs')
        for name, spec in inventory['files'].items():
            raw = archive.read(name)
            exact(spec, {'bytes': len(raw), 'sha256': sha(raw)}, 'prefix member bytes differ')
        for ordinal in range(PREFIX_ATTEMPTS):
            prefix = f'{ordinal:05d}'
            request = state.request()
            exact(parse(archive.read(prefix + '.intent.json'))['request'], request, 'prefix request differs')
            state.accept(request, {'status': 200, 'body': archive.read(prefix + '.body.json'),
                'complete': True, 'encoding': 'identity'})
        prior = parse(archive.read('report.json'))
        exact(state.results, prior['results'], 'completed daily prefix differs')
        require(state.current is not None and len(state.current.rows) == 1000
            and state.request()['page'] == 2, 'exact continuation point differs')
    return state


def report(state, attempts, failure):
    return seal({'contract_id': ID, 'protocol_complete': failure is None and len(state.results) == len(state.tasks),
        'new_attempt_count': attempts, 'reused_attempt_count': PREFIX_ATTEMPTS,
        'total_attempt_count': attempts + PREFIX_ATTEMPTS, 'prefix_pin': PREFIX_PIN,
        'receipt_schema': old.ID, 'failure': failure, 'results': deepcopy(state.results), **old.b.BOUNDARY})


class Capture(old.Capture):
    def __init__(self, contract, panel, *, prefix_path, root, **kwargs):
        state = replay_prefix(prefix_path, panel, root)
        super().__init__(contract, panel, **kwargs)
        self.state = state
        self.store.write('prefix.zip', Path(prefix_path).read_bytes(), payload=True)

    def once(self, request):
        require(self.attempts < MAX_NEW_ATTEMPTS, 'remaining attempt ceiling')
        return super().once(request)

    def run(self):
        require(not self.finished and self.attempts == 0, 'continuation cannot restart')
        failure = None
        try:
            while (request := self.state.request()) is not None:
                failure = self.once(request)
                if failure: break
        except BaseException:
            failure = 'interrupted'
            raise
        finally:
            self.finished = True
            result = report(self.state, self.attempts, failure)
            raw = render(result)
            require(len(raw) <= old.REPORT_RESERVE, 'bounded report required')
            self.store.write('report.json', raw, payload=True)
            self.store.write('inventory.json', render(seal({'contract_id': ID, 'files': dict(self.store.files)})))
        return result


def verify_archive(path, *, expected_bytes, expected_sha256, expected_inventory_sha256, contract, panel, root, prefix_output):
    path = Path(path)
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents))
        and type(expected_bytes) is int and 0 < expected_bytes <= old.MAX_TOTAL and path.stat().st_size == expected_bytes,
        'continuation ZIP size/path differs')
    with path.open('rb') as handle:
        require(hashlib.file_digest(handle, 'sha256').hexdigest() == expected_sha256, 'original continuation ZIP SHA differs')
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = {i.filename for i in infos}
        require(len(names) == len(infos) and len(names) <= MAX_NEW_ATTEMPTS * 3 + 4, 'archive population ceiling')
        payload_bytes = sum(i.file_size for i in infos if i.filename in ('prefix.zip', 'report.json') or i.filename.endswith('.body.json'))
        require(payload_bytes <= old.MAX_PAYLOAD and sum(i.file_size for i in infos) - payload_bytes <= old.MAX_METADATA,
            'archive payload/metadata ceiling')
        for info in infos:
            require(re.fullmatch(r'(?:contract|inventory|report)\.json|prefix\.zip|[0-9]{5}\.(?:intent|receipt|body)\.json', info.filename)
                and not info.is_dir() and stat.S_IFMT(info.external_attr >> 16) in (0, stat.S_IFREG)
                and info.file_size <= (PREFIX_PIN['bytes'] if info.filename == 'prefix.zip' else
                    old.REPORT_RESERVE if info.filename == 'report.json' else old.daily.MAX_BODY if info.filename.endswith('.body.json')
                    else old.MAX_METADATA), 'unsafe archive member')
        raw = archive.read('inventory.json')
        require(sha(raw) == expected_inventory_sha256, 'independent continuation inventory differs')
        saved = parse(raw)
        old.d.base.verify_seal(saved)
        require(set(saved) == {'contract_id', 'files', 'content_sha256'} and saved['contract_id'] == ID
            and set(saved['files']) == names - {'inventory.json'}, 'inventory population differs')
        for name, spec in saved['files'].items():
            raw = archive.read(name)
            exact(spec, {'bytes': len(raw), 'sha256': sha(raw)}, 'original member bytes differ')
        exact(parse(archive.read('contract.json')), contract, 'continuation contract differs')
        prefix_output = Path(prefix_output)
        require(not any(p.is_symlink() for p in (prefix_output, *prefix_output.parents)), 'regular prefix output required')
        with prefix_output.open('xb') as handle: handle.write(archive.read('prefix.zip'))
        state = replay_prefix(prefix_output, panel, root)
        count, last = 0, {}
        while (request := state.request()) is not None:
            require(count < MAX_NEW_ATTEMPTS, 'archive suffix attempt ceiling')
            prefix = f'{count:05d}'
            intent, receipt = (parse(archive.read(prefix + '.' + name + '.json')) for name in ('intent', 'receipt'))
            started, provider = intent['started_monotonic_ns'], request['provider']
            require(type(started) is int and started >= 0 and (provider not in last
                or started - last[provider] >= old.INTERVAL_NS[provider]), 'archive pacing differs')
            last[provider] = started
            begin, end = (datetime.fromisoformat(v) for v in (intent['started_at'], receipt['finished_at']))
            require(begin.tzinfo is not None and end.tzinfo is not None and begin <= end, 'archive clock differs')
            exact(intent, seal({'contract_id': old.ID, 'ordinal': count, 'request': request,
                'started_at': intent['started_at'], 'started_monotonic_ns': started}), 'archive intent differs')
            raw = archive.read(prefix + '.body.json')
            exact(receipt, seal({'contract_id': old.ID, 'ordinal': count, 'intent_sha256': intent['content_sha256'],
                'finished_at': receipt['finished_at'], 'status': 200, 'complete': True,
                'body_bytes': len(raw), 'body_sha256': sha(raw), 'body_retained': True, 'error': None}), 'archive receipt differs')
            state.accept(request, {'status': 200, 'body': raw, 'complete': True, 'encoding': 'identity'})
            count += 1
        require(len(names) == count * 3 + 4, 'extra files after exhaustion')
        exact(parse(archive.read('report.json')), report(state, count, None), 'continuation report differs')
    return seal({'contract_id': ID, 'protocol_complete': True, 'new_attempt_count': count,
        'reused_attempt_count': PREFIX_ATTEMPTS, 'total_attempt_count': count + PREFIX_ATTEMPTS,
        'archive_bytes': expected_bytes, 'archive_sha256': expected_sha256,
        'inventory_file_sha256': expected_inventory_sha256, 'completed_tasks': len(state.results),
        'verified_member_count': len(names), **old.b.BOUNDARY})
