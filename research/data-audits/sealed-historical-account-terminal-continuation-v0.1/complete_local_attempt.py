"""Follow the existing native replay; never start or repeat a replay."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import time

BASE = Path('/workspace/scratch/c5db64c94584')
REPO = BASE / 'momentumbot'
ATTEMPT = BASE / 'terminal-continuation-local-attempt-01'
STATE = BASE / 'TERMINAL_CONTINUATION_STATE.json'
REGISTRATION = '0f2570ba5b71783c3d27b47f2718217d7331bba8a2e8f7f09527c097fdf4a3fb'
PYTHON = '/workspace/scratch/193af10e3424/quote-env/bin/python'


def write_once(name, value):
    with (ATTEMPT / name).open('x') as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write('\n')


def main():
    write_once('verification-follower-start.json', {
        'purpose': 'verify_completed_existing_replay_once',
        'local_native_session': 56228, 'registration_freeze': REGISTRATION,
        'replay_will_not_be_started_or_repeated': True,
        'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat()})
    deadline = time.monotonic() + 6 * 60 * 60
    while time.monotonic() < deadline:
        if (ATTEMPT / 'account-replay-failure.json').exists():
            raise RuntimeError('native replay failure preserved; verification not started')
        lines = (BASE / 'terminal-continuation-local-attempt-01.log').read_text().splitlines()
        try:
            final = json.loads(lines[-1]) if lines else {}
        except json.JSONDecodeError:
            final = {}
        if 'runtime_content_sha256' in final:
            if final.get('paths') != 12 or final.get('sessions') != 360:
                raise ValueError('native final population differs')
            break
        time.sleep(10)
    else:
        raise TimeoutError('existing native replay has not completed within follower deadline')
    state = json.loads(STATE.read_text())
    command = [PYTHON, 'scripts/verify_sealed_historical_account_terminal_continuation_v01.py',
        '--runtime-root', str(ATTEMPT / 'account-replay'),
        '--binding-root', state['binding_root'], '--parent-runtime-root', state['parent_runtime_root'],
        '--management-zip', state['source_archives']['management']['path'],
        '--exit-zip', state['source_archives']['exit']['path'],
        '--expected-registration-sha256', REGISTRATION,
        '--expected-runtime-sha256', final['runtime_content_sha256'],
        '--output', str(ATTEMPT / 'account-replay/independent-verification.json')]
    write_once('independent-verification-attempt.json', {
        'registration_freeze': REGISTRATION, 'runtime_content_sha256': final['runtime_content_sha256'],
        'command': command, 'automatic_retries_authorized': False})
    log = BASE / 'terminal-continuation-local-independent-verification-01.log'
    with log.open('x') as handle:
        result = subprocess.run(command, cwd=REPO, stdout=handle, stderr=subprocess.STDOUT)
    write_once('independent-verification-process-result.json', {
        'exit_code': result.returncode, 'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest(),
        'runtime_content_sha256': final['runtime_content_sha256'],
        'completed_at': datetime.datetime.now(datetime.timezone.utc).isoformat()})
    return result.returncode


if __name__ == '__main__':
    try:
        code = main()
    except Exception as exc:
        write_once('verification-follower-failure.json', {'error_type': type(exc).__name__, 'error': str(exc)})
        raise
    raise SystemExit(code)
