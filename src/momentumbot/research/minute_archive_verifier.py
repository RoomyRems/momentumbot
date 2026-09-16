"""Shared original-byte archive replay for additive minute captures."""
from datetime import datetime
import re
import stat
import zipfile

def verify_minute_archive(path, metadata, inventory_sha256, contract, *, protocol):
    """Replay a bounded minute protocol using its own state and ceilings."""
    old, c, daily = protocol.old, protocol.c, protocol.daily
    require, exact, seal, sha, parse = protocol.require, protocol.exact, protocol.seal, protocol.sha, protocol.parse
    MAX_TOTAL, MAX_ATTEMPTS = protocol.MAX_TOTAL, protocol.MAX_ATTEMPTS
    MAX_PAYLOAD, MAX_METADATA = protocol.MAX_PAYLOAD, protocol.MAX_METADATA
    State, ID = protocol.State, protocol.ID
    """Stream original members through the minute parser; never retain all bars."""
    old.parent.parent._pinned_file(path, {'bytes': metadata['size_in_bytes'], 'sha256': metadata['digest'][7:]})
    require(0 < metadata['size_in_bytes'] <= MAX_TOTAL, 'bounded original archive required')
    state, count, last, first = State(contract['requests']), 0, None, None
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = {i.filename for i in infos}
        require(len(names) == len(infos) <= MAX_ATTEMPTS * 3 + 3 and sum(i.file_size for i in infos) <= MAX_TOTAL,
            'bounded unique archive members required')
        payload_bytes = sum(i.file_size for i in infos if i.filename.endswith('.body.json') or i.filename == 'report.json')
        require(payload_bytes <= MAX_PAYLOAD and sum(i.file_size for i in infos) - payload_bytes <= MAX_METADATA,
            'archive retention ceilings')
        for info in infos:
            require(re.fullmatch(r'(?:contract|inventory|report)\.json|[0-9]{5}\.(?:intent|receipt|body)\.json', info.filename)
                and not info.is_dir() and stat.S_IFMT(info.external_attr >> 16) in (0, stat.S_IFREG)
                and info.file_size <= (daily.MAX_BODY if info.filename.endswith('.body.json') else
                    c.REPORT_RESERVE if info.filename == 'report.json' else c.MAX_METADATA), 'unsafe archive member')
        raw = archive.read('inventory.json')
        require(sha(raw) == inventory_sha256, 'independent inventory differs')
        inventory = parse(raw)
        c.d.base.verify_seal(inventory)
        require(set(inventory) == {'contract_id', 'files', 'content_sha256'} and inventory['contract_id'] == c.ID
            and set(inventory['files']) == names - {'inventory.json'}, 'inventory population differs')
        for name, spec in inventory['files'].items():
            raw = archive.read(name)
            exact(spec, {'bytes': len(raw), 'sha256': sha(raw)}, 'original member differs')
        exact(parse(archive.read('contract.json')), contract, 'captured contract differs')
        while (request := state.request()) is not None:
            require(count < MAX_ATTEMPTS, 'archive attempt ceiling')
            prefix = f'{count:05d}'
            intent, receipt = (parse(archive.read(prefix + '.' + k + '.json')) for k in ('intent', 'receipt'))
            started = intent['started_monotonic_ns']
            require(type(started) is int and started >= 0 and (last is None or started - last >= c.INTERVAL_NS['alpaca']),
                'archive pacing differs')
            if first is None: first = started
            require(started - first < c.MAX_DURATION_NS, 'archive duration ceiling')
            last = started
            begin, end = (datetime.fromisoformat(v) for v in (intent['started_at'], receipt['finished_at']))
            require(begin.tzinfo is not None and end.tzinfo is not None and begin <= end, 'archive clocks differ')
            exact(intent, seal({'contract_id': c.ID, 'ordinal': count, 'request': request,
                'started_at': intent['started_at'], 'started_monotonic_ns': started}), 'intent differs')
            body = archive.read(prefix + '.body.json')
            exact(receipt, seal({'contract_id': c.ID, 'ordinal': count, 'intent_sha256': intent['content_sha256'],
                'finished_at': receipt['finished_at'], 'status': 200, 'complete': True, 'body_bytes': len(body),
                'body_sha256': sha(body), 'body_retained': True, 'error': None}), 'receipt differs')
            state.accept(request, {'status': 200, 'body': body, 'complete': True, 'encoding': 'identity'})
            count += 1
        require(len(names) == count * 3 + 3, 'extra or missing capture members')
        exact(parse(archive.read('report.json')), c.report(state, count, None), 'original report replay differs')
    return seal({'contract_id': ID, 'archive_metadata': metadata, 'inventory_sha256': inventory_sha256,
        'protocol_complete': True, 'attempt_count': count, 'verified_member_count': len(names),
        'requests_complete': len(state.results), 'bar_count': sum(r['bar_count'] for r in state.results),
        'symbol_dates': sum(len(r['symbol_bar_counts']) for r in state.results),
        'empty_symbol_dates': sum(len(r['empty_symbols']) for r in state.results),
        'root_summaries': state.results, 'provider_requests': 0, **old.parent.parent.BOUNDARY})

