"""Bounded prior daily history for the frozen candidate population."""
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import sys

from momentumbot.research import candidate_raw_minutes as parent
from momentumbot.research.minute_archive_verifier import verify_minute_archive

old, c, daily, gate = parent.old, parent.c, parent.daily, parent.gate
require, exact, seal, sha, render, parse = parent.require, parent.exact, parent.seal, parent.sha, parent.render, parent.parse
ID = 'early-pullback-candidate-daily-history-v0.1'
BASE = 'research/data-audits/' + ID
CONTRACT_PATH = 'research/strategy/' + ID + '.json'
WORKFLOW = '.github/workflows/candidate-daily-history.yml'
PARENT = '54ba261fe9ed6f003f39812932d3812c0a6dd6d2'
REF = 'refs/tags/' + ID + '-consumed'
KEYS = parent.KEYS
MAX_ATTEMPTS = 600
MAX_PAYLOAD, MAX_METADATA = c.MAX_PAYLOAD, c.MAX_METADATA
MAX_TOTAL = MAX_PAYLOAD + MAX_METADATA
SUPERSET_PATH = old.BASE + '/saved-daily-acquisition-superset.json.gz'
SUPERSET_SEAL = '92c9616b3a9c88f24aece25d181e858faeb9b5c703e53e2b4695309f61cda4ac'
FILES = ('src/momentumbot/research/candidate_daily_history.py',
    'src/momentumbot/research/minute_archive_verifier.py',
    'scripts/hosted_scanner_source_cli.py', 'scripts/run_candidate_daily_history.py',
    'tests/test_candidate_daily_history.py', WORKFLOW, SUPERSET_PATH,
    '.github/actions/source-runtime/action.yml', '.github/workflows/ci.yml',
    'requirements-sealed-source-v04.txt')


def history_root(raw_root):
    """Keep the exact dated candidate batch; request only prior daily bars."""
    c.d.base.verify_seal(raw_root)
    require(raw_root['params']['adjustment'] == 'raw'
        and raw_root['params']['timeframe'] == '1Min', 'frozen raw candidate root required')
    target = date.fromisoformat(raw_root['trading_date'])
    start = datetime.combine(target - timedelta(days=120), time(), daily.ET)
    end = datetime.combine(target, time(), daily.ET) - timedelta(seconds=1)
    return seal({**{k: v for k, v in raw_root.items() if k != 'content_sha256'},
        'params': {**raw_root['params'], 'timeframe': '1Day', 'adjustment': 'split',
            'start': start.astimezone(timezone.utc).isoformat(),
            'end': end.astimezone(timezone.utc).isoformat()}})


def request_plan(root):
    return [history_root(r) for r in parent.validate_registration(root)['requests']]


def registration(root):
    inherited = parent.validate_registration(root)
    return seal({'contract_id': ID, 'contract_path': CONTRACT_PATH, 'workflow': WORKFLOW,
        'parent_commit': PARENT, 'parent_registration_sha256': inherited['content_sha256'],
        'acquisition_superset_sha256': SUPERSET_SEAL, 'requests': request_plan(root),
        'file_bindings': {n: {'bytes': (Path(root) / n).stat().st_size,
            'sha256': sha((Path(root) / n).read_bytes())} for n in FILES},
        'authorization': {**inherited['authorization'], 'user_message': 'Great you may continue development; Continue',
            'scope': 'one split 1Day SIP capture for 120 calendar days strictly before each of the existing 4018 candidate symbol/date cases; same 30 target dates; no subscription or product changes'},
        'limits': {**inherited['limits'], 'maximum_attempts': MAX_ATTEMPTS,
            'maximum_payload_bytes': MAX_PAYLOAD, 'maximum_metadata_bytes': MAX_METADATA},
        'runtime': inherited['runtime'], 'consumption_ref': REF, 'credential_names': list(KEYS),
        'receipt_and_report_schema': c.ID,
        'timestamp_semantics': 'daily session start; only sessions strictly before target date',
        'prior_session_count_required': 50,
        'missing_history_rule': 'explicit insufficient history; never pad missing sessions',
        'source_role': 'prior daily session inventory and 50-session average split volume; never exact RVOL',
        'acquisition_filter_values_allowed_in_runtime': False,
        'daily_minute_share_basis_verified': False,
        'exact_same_time_rvol_complete': False, **old.parent.parent.BOUNDARY})


def validate_registration(root):
    value = parse((Path(root) / CONTRACT_PATH).read_bytes())
    exact(value, registration(root), 'candidate daily history registration differs')
    return value


class DailyPages(parent.parent.MinutePages):
    """Reuse strict OHLC/cursor checks; add unique prior local-session dates."""
    def __init__(self, root):
        super().__init__(root)
        require(root['params']['timeframe'] == '1Day'
            and root['params']['adjustment'] == 'split', 'split daily root required')
        self.sessions = {s: set() for s in self.symbols}

    def _accept(self, request, reply):
        observed = {s: set(v) for s, v in self.sessions.items()}
        payload = parse(reply['body'])
        for symbol, rows in (payload.get('bars') or {}).items():
            require(symbol in observed, 'unrequested daily symbol')
            for row in rows:
                session = daily._stamp(row['t']).astimezone(daily.ET).date()
                require(session < date.fromisoformat(self.root['trading_date']), 'target/future daily bar forbidden')
                require(session not in observed[symbol], 'duplicate daily session')
                observed[symbol].add(session)
        result = super()._accept(request, reply)
        self.sessions = observed
        return result

    def result(self):
        result = super().result()
        result.pop('content_sha256')
        sessions = {s: sorted(d.isoformat() for d in days)[-50:] for s, days in self.sessions.items()}
        return seal({**result, 'prior_sessions_by_symbol': sessions,
            'insufficient_history_symbols': [s for s, dates in sessions.items() if len(dates) < 50]})


class State(parent.State):
    def request(self):
        require(not self.failed, 'daily history state failed')
        if len(self.results) == len(self.tasks): return None
        if self.current is None: self.current = DailyPages(self.tasks[len(self.results)])
        return self.current.request()


class Capture(old.Capture):
    def __init__(self, contract, **kwargs):
        super().__init__(contract, **kwargs)
        self.state = State(contract['requests'])

    def once(self, request):
        require(self.attempts < MAX_ATTEMPTS, 'candidate daily history attempt ceiling')
        return super().once(request)


Transport = old.Transport


def verify_archive(path, metadata, inventory_sha256, contract):
    return verify_minute_archive(path, metadata, inventory_sha256, contract,
        protocol=sys.modules[__name__])


def preflight(root, env, facts, now, runtime, path, metadata, live_ref):
    contract = validate_registration(root)
    gate.check_launch(contract, env, facts, now)
    gate.verify_preflight(old.parent.read_archive(path, metadata['size_in_bytes'], metadata['digest'][7:]),
        contract, env, runtime, live_ref, metadata)
    return contract


def capture(root, env, facts, now, runtime, path, metadata, live_ref, *, output, credential_loader, transport, progress):
    contract = preflight(root, env, facts, now, runtime, path, metadata, live_ref)
    require(not Path(output).exists() and not any(p.is_symlink() for p in (Path(output), *Path(output).parents)),
        'fresh output required')
    return Capture(contract, output=output, keys=credential_loader(), transport=transport, progress=progress).run()


def verify(root, env, facts, now, runtime, path, metadata, live_ref, capture_path, capture_metadata, jobs):
    contract = preflight(root, env, facts, now, runtime, path, metadata, live_ref)
    gate.check_jobs(jobs, env)
    gate.check_artifact(capture_metadata, contract, env, 'capture', env['CAPTURE_ARTIFACT_ID'], MAX_TOTAL)
    result = verify_archive(capture_path, capture_metadata, env['CAPTURE_INVENTORY_SHA256'], contract)
    return seal({'contract_id': ID, 'code_commit': env['GITHUB_SHA'], 'run_id': env['GITHUB_RUN_ID'],
        'archive_verification': result, 'hosted_capture_provenance_verified': True,
        'consumption_ref': REF, 'provider_requests_during_verification': 0,
        'daily_minute_share_basis_verified': False, 'exact_same_time_rvol_complete': False,
        **old.parent.parent.BOUNDARY})


def project_history_root(root, pages, expected):
    """Project already authenticated pages; this function authenticates no origin."""
    import pandas as pd
    from momentumbot.historical_data_v03 import _average_volume_before
    parser = DailyPages(root)
    rows = {s: [] for s in root['params']['symbols'].split(',')}
    for request, body in pages:
        parser.accept(request, {'status': 200, 'complete': True, 'encoding': 'identity', 'body': body})
        for symbol, bars in (parse(body)['bars'] or {}).items():
            rows[symbol].extend((r['t'], r['c'], r['v']) for r in bars)
    result = parser.result()
    exact(result, expected, 'accepted daily history projection differs')
    output = {}
    for symbol, values in rows.items():
        frame = pd.DataFrame(values, columns=['timestamp', 'close', 'volume'])
        frame.index = pd.to_datetime(frame.pop('timestamp'), utc=True)
        average = _average_volume_before(frame, date.fromisoformat(root['trading_date']), sessions=50)
        output[symbol] = {'daily_bars': frame,
            'prior_sessions': result['prior_sessions_by_symbol'][symbol],
            'average_daily_volume_50': average,
            'sufficient_history': len(result['prior_sessions_by_symbol'][symbol]) == 50}
    return output
