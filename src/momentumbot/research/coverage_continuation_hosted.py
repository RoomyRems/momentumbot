"""Contract-specific binding for the reusable hosted source gate."""
from pathlib import Path

from momentumbot.research import coverage_continuation as c
from momentumbot.research import hosted_source_gate as gate
from momentumbot.research.census_payload_evidence import read_archive

ID = c.ID
PARENT = '887544eb55de494bcb9cf07d441a3669f2f4b220'
CONTRACT_PATH = 'research/strategy/' + ID + '.json'
WORKFLOW = '.github/workflows/coverage-continuation.yml'
REF = 'refs/tags/' + ID + '-consumed'
FILES = ('src/momentumbot/research/coverage_continuation.py',
    c.PREFIX_PATH,
    'src/momentumbot/research/coverage_continuation_hosted.py', 'src/momentumbot/research/hosted_source_gate.py',
    'scripts/run_coverage_continuation.py', 'tests/test_coverage_continuation.py', WORKFLOW,
    '.github/actions/source-runtime/action.yml', '.github/workflows/ci.yml', 'requirements-sealed-source-v04.txt',
    'research/data-audits/' + c.old.ID + '/failure-verification.json',
    'research/data-audits/' + c.old.ID + '/rejected-corporate-actions.json')


def registration(root):
    parent = c.parent.validate_registration(root)
    c.verify_saved_failure(root)
    return c.seal({'contract_id': ID, 'contract_path': CONTRACT_PATH, 'workflow': WORKFLOW,
        'parent_commit': PARENT, 'parent_registration_sha256': parent['content_sha256'],
        'file_bindings': {name: {'bytes': (Path(root) / name).stat().st_size,
            'sha256': c.sha((Path(root) / name).read_bytes())} for name in FILES},
        'selected_dates': list(c.old.b.DATES), 'panel_sha256': c.old.daily.PANEL_SEAL,
        'prefix_pin': c.PREFIX_PIN, 'failure_verification_sha256': c.FAILURE_SEAL,
        'limits': {**parent['limits'], 'maximum_new_attempts': c.MAX_NEW_ATTEMPTS, 'reused_attempts': c.PREFIX_ATTEMPTS},
        'authorization': {**parent['authorization'], 'user_message': 'You may continue',
            'starts_at': '2026-09-14T00:00:00Z', 'expires_at': '2026-09-21T00:00:00Z',
            'scope': 'one separately consumed continuation after replaying all 47 exact saved responses; remaining fixed suffix only'},
        'consumption_ref': REF, 'runtime': parent['runtime'], 'credential_names': list(c.old.KEYS),
        'repair': 'Alpaca process-date arrival order becomes a retained diagnostic; no sorting, deduplication or relaxed date/ID/cursor checks',
        'receipt_schema': c.old.ID, 'automatic_original_archive_verification': True, **c.old.b.BOUNDARY})


def validate_registration(root):
    saved = c.parse((Path(root) / CONTRACT_PATH).read_bytes())
    c.exact(saved, registration(root), 'continuation registration differs')
    return saved


def check_prefix_artifact(value):
    env = {'GITHUB_SHA': c.PREFIX_PIN['code_commit'], 'GITHUB_RUN_ID': str(c.PREFIX_PIN['run_id'])}
    c.parent.check_artifact(value, env, 'capture', str(c.PREFIX_PIN['artifact_id']), c.old.MAX_TOTAL)
    c.require(value['size_in_bytes'] == c.PREFIX_PIN['bytes'] and value['digest'] == 'sha256:' + c.PREFIX_PIN['sha256'],
        'original prefix artifact differs')


def check_preflight_zip(path, metadata, contract, env, runtime, live_ref):
    gate.check_artifact(metadata, contract, env, 'consumption', env.get('PREFLIGHT_ARTIFACT_ID'), gate.d.previous.PREFLIGHT_LIMIT)
    files = read_archive(path, metadata['size_in_bytes'], metadata['digest'][7:])
    gate.verify_preflight(files, contract, env, runtime, live_ref, metadata)


def capture(root, env, facts, now, runtime, preflight_zip, metadata, live_ref, prefix_path, prefix_metadata,
        *, output, credential_loader, transport, progress, session_factory=c.Capture):
    contract = validate_registration(root)
    gate.check_launch(contract, env, facts, now)
    check_preflight_zip(preflight_zip, metadata, contract, env, runtime, live_ref)
    check_prefix_artifact(prefix_metadata)
    output = Path(output)
    c.require(not output.exists() and not any(p.is_symlink() for p in (output, *output.parents)), 'fresh output required')
    panel = c.old.daily.load_panel(root)
    c.replay_prefix(prefix_path, panel, root)  # must complete before the key loader
    return session_factory(contract, panel, prefix_path=prefix_path, root=root, output=output,
        keys=credential_loader(), transport=transport, progress=progress).run()


def verify(root, env, facts, now, runtime, preflight_zip, preflight_metadata, live_ref, capture_zip, capture_metadata, jobs, prefix_output):
    contract = validate_registration(root)
    gate.check_launch(contract, env, facts, now)
    check_preflight_zip(preflight_zip, preflight_metadata, contract, env, runtime, live_ref)
    gate.check_jobs(jobs, env)
    gate.check_artifact(capture_metadata, contract, env, 'capture', env.get('CAPTURE_ARTIFACT_ID'), c.old.MAX_TOTAL)
    result = c.verify_archive(capture_zip, expected_bytes=capture_metadata['size_in_bytes'],
        expected_sha256=capture_metadata['digest'][7:], expected_inventory_sha256=env.get('CAPTURE_INVENTORY_SHA256'),
        contract=contract, panel=c.old.daily.load_panel(root), root=root, prefix_output=prefix_output)
    return c.seal({'contract_id': ID, 'code_commit': env['GITHUB_SHA'], 'run_id': env['GITHUB_RUN_ID'],
        'archive_verification': result, 'hosted_capture_provenance_verified': True,
        'consumption_ref': REF, 'capture_artifact_id': capture_metadata['id'],
        'preflight_artifact_id': preflight_metadata['id'], 'provider_requests_during_verification': 0, **c.old.b.BOUNDARY})
