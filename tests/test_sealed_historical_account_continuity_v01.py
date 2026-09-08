from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from momentumbot.research import sealed_historical_account_continuity_v01 as m
from tests.test_sealed_historical_account_scheduler_v01 import (
    empty_program as scheduler_program, attach, spec, repin, changed_entry,
    cases as scheduler_cases, reseal, BASE, SECOND, MS, record, runtime, state, decisions)
from tests.test_sealed_historical_account_valuation_v01 import fixture as valued_fixture

ROOT = Path(__file__).resolve().parents[1]


def empty_program(**kwargs):
    p = scheduler_program(**kwargs)
    p['contract_id'] = m.CONTRACT_ID
    return reseal(p)


def campaign_program(*, entries=3, scenario='l1-conservative-v0.1', count=1,
                     account='main_account', second_options=None):
    p = empty_program(count=count, scenario=scenario, account=account)
    first = spec(final_price='11', scenario=scenario, account=account,
                 **({'quantity': 4, 'target_fill': 2, 'final_fill': 2} if account == 'small_account' else {}))
    p = attach(p, 0, first)
    for i in range(1, entries):
        options = dict(offset=i * 3 * SECOND, final_price='11', scenario=scenario, account=account)
        if account == 'small_account':
            options.update(quantity=4, target_fill=2, final_fill=2)
        if i == 1:
            options.update(second_options or {})
        item = spec(**options)
        decision = item['entry_input']['source_decision']
        decision.update(activation_id=first['entry_input']['source_decision']['activation_id'],
                        candidate_qualified_at=first['entry_input']['source_decision']['candidate_qualified_at'])
        p = attach(p, 0, repin(item))
    return p


def replay(p):
    return m.replay_path(p, expected_program_content_sha256=p['content_sha256'])


def verify(p, r):
    return m.verify_path(p, r, expected_program_content_sha256=p['content_sha256'], expected_result_content_sha256=r['content_sha256'])


def checkpoint(p, at):
    return m.checkpoint_path(p, through_ns=at, expected_program_content_sha256=p['content_sha256'])


def resume(p, c, **kwargs):
    return m.resume_path(p, c, expected_program_content_sha256=p['content_sha256'],
                         expected_checkpoint_content_sha256=c['content_sha256'], **kwargs)


def snapshot(r):
    return runtime(r)['reconciliation_snapshot']


def case_programs():
    result = {scenario + '-reentry': campaign_program(scenario=scenario) for scenario in m.feedback.SCENARIOS}
    result['small-reentry'] = campaign_program(account='small_account')
    result['reentry-open'] = campaign_program(entries=2, second_options={'target_fill': 2, 'final_fill': 3})
    result['reentry-cash-carry'] = campaign_program(entries=2, count=2)
    for name in ('collision', 'delayed', 'unfilled', 'partial_carry', 'pending_input_failure', 'omitted', 'unavailable', 'risk_flatten'):
        p = scheduler_cases()[name]
        p['contract_id'] = m.CONTRACT_ID
        result[name] = reseal(p)
    p = attach(empty_program(count=1), 0, spec(final_price='11'))
    result['new-activation'] = attach(p, 0, spec('A', offset=3 * SECOND, final_price='11'))
    return result


def synthetic_vectors():
    programs = case_programs()
    for account in ('main_account', 'small_account'):
        for horizon in (1, 5, 10):
            for scenario in m.feedback.SCENARIOS:
                p = empty_program(account=account, horizon=horizon, scenario=scenario)
                programs['empty-' + p['path_id']] = p
    vectors = []
    for name, p in programs.items():
        r = replay(p)
        checkpoints = []
        if name in ('l1-conservative-v0.1-reentry', 'l1-stress-v0.1-reentry', 'reentry-open', 'delayed', 'unfilled'):
            # A checkpoint always lies in the last included original session.
            p1 = deepcopy(p)
            p1['sessions'] = p1['sessions'][:1]
            p1 = reseal(p1)
            r1 = replay(p1)
            for offset in (0, 100 * MS, 450 * MS, SECOND, 1100 * MS, 3100 * MS, 5100 * MS, 960 * SECOND):
                c = checkpoint(p1, BASE + offset)
                continued = resume(p1, c)
                if continued != r1:
                    raise ValueError('resume differs from uninterrupted path')
                checkpoints.append({'program': p1, 'checkpoint': c, 'resumed_result_content_sha256': continued['content_sha256'],
                    'uninterrupted_result': r1})
        vectors.append({'name': name, 'program': p, 'result': r, 'verification': verify(p, r), 'checkpoints': checkpoints})
    return m.seal({'contract_id': m.CONTRACT_ID, 'synthetic_only': True, 'vectors': vectors, **m.BOUNDARY})


class ContinuityMechanicsTests(unittest.TestCase):
    def test_two_entries_one_campaign_third_is_blocked(self):
        for scenario in m.feedback.SCENARIOS:
            p = campaign_program(scenario=scenario)
            r = replay(p)
            self.assertIsNone(runtime(r)['failure'])
            self.assertEqual([d['disposition'] for d in decisions(r)], ['entry_submitted', 'entry_submitted', 'blocked_campaign_entry_limit'])
            campaign = snapshot(r)['ledger']['campaigns'][0]
            self.assertEqual((campaign['entry_fill_count'], campaign['reentry_count']), (2, 1))
            buys = [j['execution_evidence'] for j in snapshot(r)['journal'] if j['fee_application']['trade']['side'] == 'buy']
            self.assertEqual([e['entry_role'] for e in buys], ['starter', 'reentry'])
            self.assertNotEqual(buys[0]['fill_id'], buys[1]['fill_id'])
            self.assertTrue(verify(p, r)['verification_passed'])

    def test_campaign_history_fees_and_exact_cash_persist(self):
        r = replay(campaign_program(entries=2, count=2))
        self.assertEqual(state(r)['equity_usd'], '30029.98')
        self.assertEqual(state(r, 1)['equity_usd'], '30029.98')
        self.assertEqual(state(r)['cumulative_fees_usd'], '0.02')
        position = next(iter(snapshot(r)['exact_account']['positions'].values()))
        self.assertEqual(Decimal(position['gross_realized_pnl']), Decimal(30))
        self.assertEqual(Decimal(position['fees_charged']), Decimal('.02'))
        self.assertEqual(len(position['entry_fill_ids']), 2)
        self.assertEqual(r['seed_application_count'], 1)

    def test_small_account_keeps_frozen_risk_sizing(self):
        r = replay(campaign_program(account='small_account'))
        self.assertIsNone(runtime(r)['failure'])
        buys = [j['fee_application']['trade']['quantity'] for j in snapshot(r)['journal'] if j['fee_application']['trade']['side'] == 'buy']
        self.assertEqual(buys, [4, 4])
        self.assertEqual(state(r)['equity_usd'], '2011.98')

    def test_same_symbol_new_activation_is_a_new_campaign(self):
        r = replay(case_programs()['new-activation'])
        self.assertEqual(len(snapshot(r)['ledger']['campaigns']), 2)
        self.assertEqual([j['execution_evidence']['entry_role'] for j in snapshot(r)['journal'] if j['fee_application']['trade']['side'] == 'buy'], ['starter', 'starter'])

    def test_reentry_has_fresh_target_and_stop(self):
        p = campaign_program(entries=2)
        c = checkpoint(p, BASE + 3100 * MS)
        engine = c['reconciliation_snapshot']['management']
        self.assertEqual(engine['entry']['entry_role'], 'reentry')
        self.assertFalse(engine['target_attempted'])
        self.assertFalse(engine['full_exit_attempted'])
        self.assertFalse(engine['breakeven_active'])
        self.assertEqual(engine['active_stop_price'], 9)
        self.assertEqual(engine['remaining_quantity'], 10)

    def test_reentry_uses_new_fill_cost_basis(self):
        p = campaign_program(entries=2, second_options={'trades': [record(2 * SECOND, 8)], 'final_fill': 10, 'final_price': '12'})
        value = p['sessions'][0]['opportunities'][1]['position']
        for row in value['entry_input']['tape']['quote_records'][:2]:
            row.update(bid_px_nanos=10_990_000_000, ask_px_nanos=11_000_000_000)
        repin(value)
        r = replay(reseal(p))
        self.assertIsNone(runtime(r)['failure'])
        last = snapshot(r)['journal'][-1]
        self.assertEqual(last['execution_evidence']['quantity'], 10)
        self.assertEqual(Decimal(last['gross_realized_delta']), Decimal(10))
        self.assertEqual(state(r)['equity_usd'], '30024.98')

    def test_unfilled_order_does_not_spend_an_entry(self):
        first = changed_entry('unfilled')
        p = attach(empty_program(count=1), 0, first)
        second = spec(offset=3 * SECOND, final_price='11')
        second['entry_input']['source_decision']['activation_id'] = first['entry_input']['source_decision']['activation_id']
        p = attach(p, 0, repin(second))
        r = replay(p)
        self.assertIsNone(runtime(r)['failure'])
        self.assertEqual(snapshot(r)['ledger']['campaigns'][0]['entry_fill_count'], 1)
        self.assertEqual(snapshot(r)['journal'][0]['execution_evidence']['entry_role'], 'starter')

    def test_ack_tie_still_blocks_reentry(self):
        for offset, expected in ((2450 * MS, 'blocked_capacity'), (2450 * MS + 1, 'entry_submitted')):
            p = campaign_program(entries=2, second_options={'offset': offset})
            self.assertEqual(decisions(replay(p))[1]['disposition'], expected)

    def test_open_partial_campaign_cannot_reenter_or_add(self):
        p = campaign_program(entries=3, second_options={'target_fill': 2, 'final_fill': 3})
        r = replay(p)
        self.assertEqual(decisions(r)[2]['disposition'], 'blocked_capacity')
        self.assertEqual(state(r)['positions'][0]['quantity'], 5)
        self.assertEqual(snapshot(r)['ledger']['campaigns'][0]['entry_fill_count'], 2)

    def test_known_guard_still_blocks_reentry(self):
        p = campaign_program(entries=2)
        first = p['sessions'][0]['opportunities'][0]['position']
        for row in first['exit_tape']['quote_records'][-2:]:
            row.update(bid_px_nanos=9_000_000_000, ask_px_nanos=9_010_000_000)
        repin(first)
        r = replay(reseal(p))
        self.assertTrue(snapshot(r)['ledger']['account']['locked'])
        self.assertEqual(decisions(r)[1]['disposition'], 'blocked_account_lock')

    def test_activation_cannot_change_symbols(self):
        p = campaign_program(entries=2)
        second = spec('B', offset=3 * SECOND)
        second['entry_input']['source_decision']['activation_id'] = p['sessions'][0]['opportunities'][0]['position']['entry_input']['source_decision']['activation_id']
        p['sessions'][0]['opportunities'].pop()
        p['slots'][0]['opportunity_inputs'].pop()
        p = attach(p, 0, repin(second))
        r = replay(p)
        self.assertIn('multiple symbols', runtime(r)['failure']['error'])
        self.assertEqual(len(snapshot(r)['journal']), 3)

    def test_checkpoint_before_fill_has_only_reservation(self):
        p = campaign_program(entries=2)
        c = checkpoint(p, BASE)
        self.assertEqual(c['reconciliation_snapshot']['journal'], [])
        self.assertEqual(c['pending_entry_reservation']['confirmed_filled_quantity'], 0)
        self.assertNotIn('outcome', json.dumps(c))
        self.assertIsNone(c['active_original_window'])
        self.assertEqual(resume(p, c), replay(p))

    def test_resume_at_entry_fill_and_ack_boundaries(self):
        for scenario, offsets in (('l1-conservative-v0.1', (99, 100, 449, 450)), ('l1-stress-v0.1', (249, 250, 549, 550))):
            p = campaign_program(entries=2, scenario=scenario)
            uninterrupted = replay(p)
            for offset in offsets:
                c = checkpoint(p, BASE + offset * MS)
                self.assertEqual(resume(p, c), uninterrupted)

    def test_resume_preserves_target_confirmation_and_pending_cancel(self):
        p = campaign_program(entries=2)
        before = checkpoint(p, BASE + SECOND)
        engine = before['reconciliation_snapshot']['management']
        self.assertTrue(engine['pending_order'])
        self.assertEqual(engine['reserved_sell_quantity'], 5)
        self.assertFalse(engine['breakeven_active'])
        after = resume(p, before, through_ns=BASE + 1100 * MS)
        engine = after['reconciliation_snapshot']['management']
        self.assertTrue(engine['pending_order'])
        self.assertTrue(engine['breakeven_active'])
        self.assertEqual(engine['reserved_sell_quantity'], 0)
        self.assertEqual(resume(p, after), replay(p))

    def test_partial_target_does_not_move_stop_during_resume(self):
        p = campaign_program(entries=2, second_options={'target_fill': 2, 'final_fill': 3})
        c = checkpoint(p, BASE + 4100 * MS)
        engine = c['reconciliation_snapshot']['management']
        self.assertEqual(engine['target_filled_quantity'], 2)
        self.assertFalse(engine['breakeven_active'])
        self.assertEqual(engine['active_stop_price'], 9)
        self.assertEqual(resume(p, c), replay(p))

    def test_terminal_partial_resume_does_not_retry(self):
        p = campaign_program(entries=2, second_options={'target_fill': 2, 'final_fill': 3,
            'trades': [record(SECOND, 12), record(2 * SECOND, 8, 1), record(3 * SECOND, 8, 2)]})
        c = checkpoint(p, BASE + 5550 * MS)
        self.assertTrue(c['reconciliation_snapshot']['management']['full_exit_attempted'])
        r = resume(p, c)
        engine = snapshot(r)['management']
        self.assertEqual(engine['remaining_quantity'], 5)
        self.assertEqual(len([e for e in engine['events'] if e['event_type'] == 'sell_submitted']), 2)

    def test_expired_window_retains_position_and_exact_state(self):
        p = campaign_program(entries=2, second_options={'target_fill': 2, 'final_fill': 3})
        end = p['sessions'][0]['opportunities'][1]['position']['entry_input']['window']['end_ns']
        c = checkpoint(p, end)
        self.assertEqual(c['status'], 'original_window_exhausted')
        r = resume(p, c)
        self.assertEqual(state(r)['positions'][0]['quantity'], 5)
        self.assertFalse(r['carried_position_execution_resumption_integrated'])
        self.assertEqual(r, replay(p))

    def test_next_session_preserves_unresolved_carried_position(self):
        p = campaign_program(entries=2, count=2, second_options={'target_fill': 2, 'final_fill': 3})
        c = checkpoint(p, m.valuation.session_start_ns(p['slots'][1]))
        self.assertEqual(c['status'], 'blocked_prior_state')
        self.assertEqual(c['opening_account_state']['positions'][0]['quantity'], 5)
        self.assertEqual(resume(p, c), replay(p))

    def test_pending_input_failure_stays_failed_after_resume(self):
        p = case_programs()['pending_input_failure']
        p['sessions'] = p['sessions'][:1]
        p = reseal(p)
        c = checkpoint(p, BASE + 15 * MS)
        self.assertEqual(c['status'], 'blocked_input_failure')
        self.assertIsNotNone(c['pending_entry_reservation'])
        self.assertEqual(resume(p, c), replay(p))

    def test_missing_exit_preserves_intent_through_resume(self):
        p = campaign_program(entries=1)
        value = p['sessions'][0]['opportunities'][0]['position']
        value['exit_tape']['quote_records'] = value['exit_tape']['quote_records'][:2]
        repin(value)
        p = reseal(p)
        c = checkpoint(p, BASE + SECOND)
        self.assertIsNotNone(c['reconciliation_snapshot']['management']['outstanding_intent'])
        self.assertEqual(resume(p, c), replay(p))

    def test_resume_preserves_used_liquidity_and_confirmed_journal(self):
        p = campaign_program(entries=2)
        c = checkpoint(p, BASE + 3100 * MS)
        self.assertEqual(len(c['reconciliation_snapshot']['consumed_sell_liquidity']), 2)
        r = resume(p, c)
        self.assertEqual(len(snapshot(r)['consumed_sell_liquidity']), 4)
        self.assertEqual(snapshot(r)['journal'][:4], c['reconciliation_snapshot']['journal'])

    def test_checkpoint_hash_and_rehashed_money_cannot_be_imported(self):
        p = campaign_program(entries=2)
        c = checkpoint(p, BASE + 3100 * MS)
        with self.assertRaises(ValueError):
            m.resume_path(p, c, expected_program_content_sha256=p['content_sha256'], expected_checkpoint_content_sha256='0' * 64)
        c['reconciliation_snapshot']['exact_account']['remaining_buying_power'] = '90000'
        c['reconciliation_snapshot'] = reseal(c['reconciliation_snapshot'])
        with self.assertRaisesRegex(ValueError, 'reconstructed continuation'):
            resume(p, reseal(c))

    def test_rehashed_stop_attempt_and_entry_history_tampering_rejected(self):
        p = campaign_program(entries=2)
        c = checkpoint(p, BASE + 4100 * MS)
        for key, value in (('active_stop_price', 1), ('target_attempted', False), ('target_filled_quantity', 0)):
            bad = deepcopy(c)
            bad['reconciliation_snapshot']['management'][key] = value
            bad['reconciliation_snapshot']['management'] = reseal(bad['reconciliation_snapshot']['management'])
            bad['reconciliation_snapshot'] = reseal(bad['reconciliation_snapshot'])
            with self.assertRaises(ValueError): resume(p, reseal(bad))

    def test_changed_source_and_cross_path_checkpoint_rejected(self):
        p = campaign_program(entries=2)
        c = checkpoint(p, BASE)
        other = campaign_program(entries=2, account='small_account')
        with self.assertRaises(ValueError): resume(other, c)
        changed = deepcopy(p)
        changed['sessions'][0]['opportunities'][1]['candidate']['percent_gain'] += 1
        with self.assertRaises(ValueError): resume(reseal(changed), c)

    def test_cutoffs_reject_backwards_and_cross_session_times(self):
        p = campaign_program(entries=2)
        c = checkpoint(p, BASE)
        for at in (BASE - 1, BASE, True):
            with self.assertRaises(ValueError): resume(p, c, through_ns=at)
        for at in (True, BASE + 86400 * SECOND, 0):
            with self.assertRaises(ValueError): checkpoint(p, at)

    def test_retrospective_keys_rejected_in_source_and_checkpoint(self):
        p = campaign_program(entries=2)
        c = checkpoint(p, BASE)
        c['ross_fill'] = 10
        with self.assertRaisesRegex(ValueError, 'retrospective'): resume(p, reseal(c))
        p['sessions'][0]['opportunities'][0]['candidate']['reasons'] = [{'ross_action': 'buy'}]
        with self.assertRaisesRegex(ValueError, 'retrospective'): replay(reseal(p))

    def test_future_execution_price_does_not_change_public_prefix(self):
        p = campaign_program(entries=2)
        before = checkpoint(p, BASE + 3 * SECOND)
        changed = deepcopy(p)
        second = changed['sessions'][0]['opportunities'][1]['position']
        second['entry_input']['tape']['quote_records'][1].update(bid_px_nanos=10_010_000_000, ask_px_nanos=10_020_000_000)
        repin(second)
        after = checkpoint(reseal(changed), BASE + 3 * SECOND)
        self.assertEqual(before['reconciliation_snapshot'], after['reconciliation_snapshot'])
        self.assertEqual(before['events'][:-1], after['events'][:-1])
        self.assertEqual(before['events'][-1]['account_before'], after['events'][-1]['account_before'])
        self.assertEqual(before['events'][-1]['disposition'], after['events'][-1]['disposition'])
        # The complete capture commitment changes; its contents cannot affect
        # the order's causal sizing, limit, lifecycle or known account state.
        for key in ('quantity', 'limit_price', 'arrival_ts_ns', 'cancel_ack_ts_ns'):
            self.assertEqual(before['events'][-1]['order'][key], after['events'][-1]['order'][key])
        self.assertEqual(before['pending_entry_reservation']['quantity'], after['pending_entry_reservation']['quantity'])

    def test_valuation_handoff_retains_open_basis_without_window_extension(self):
        f = valued_fixture(kind='open')
        slot = f['program']['slots'][f['result']['session_count']]
        session = {'session_id': slot['session_id'], 'opportunities': []}
        r = m.continue_valued_session(f['program'], f['result'], f['inputs'], session,
            expected_program_content_sha256=f['program']['content_sha256'], expected_result_content_sha256=f['result']['content_sha256'],
            expected_inputs_content_sha256=f['inputs']['content_sha256'], expected_session_sha256=m.canonical_fingerprint(session))
        self.assertTrue(r['session']['runtime']['blocked_before_execution'])
        self.assertEqual(r['seed_application_count'], 0)
        self.assertEqual(r['session']['close']['account_state']['positions'], r['valuation']['source_account_state']['positions'])


class ContinuityRegistrationTests(unittest.TestCase):
    def test_independent_checker_rejects_rehashed_campaign_and_checkpoint_state(self):
        from verify_sealed_historical_account_continuity_v01 import account_state, verify_checkpoint, read
        p = campaign_program(entries=2)
        r = replay(p)
        bad = deepcopy(snapshot(r))
        bad['ledger']['campaigns'][0]['entry_fill_count'] = 1
        with self.assertRaisesRegex(ValueError, 'counters reset'):
            account_state(reseal(bad))
        bad = deepcopy(snapshot(r))
        next(iter(bad['exact_account']['positions'].values()))['entry_price'] = '1'
        with self.assertRaisesRegex(ValueError, 'basis or totals'):
            account_state(reseal(bad))
        c = checkpoint(p, BASE + 1100 * MS)
        c['pending_entry_reservation'] = {'invented': True}
        plan = read(ROOT / 'research/runtime/sealed-historical-account-management-inputs-v0.1/account-session-input-plan.json')
        with self.assertRaisesRegex(ValueError, 'active or pending'):
            verify_checkpoint({'program': p, 'checkpoint': reseal(c), 'uninterrupted_result': r,
                'resumed_result_content_sha256': r['content_sha256']}, {v['path_id']: v for v in plan['paths']})

    def test_management_execution_methods_remain_frozen(self):
        for method in ('observe_bar', 'observe_trade', 'submit_intent', 'settle', '_advance', '_validate_clock'):
            self.assertIs(getattr(m._Management, method), getattr(m.feedback.ManagementFillFeedback, method))

    def test_registration_binds_immutable_parent_and_scope(self):
        self.assertTrue(m.validate_registration(ROOT)["verification_passed"])
        contract = m.expected_contract(ROOT)
        self.assertEqual(contract["parent_commit_sha"], "6933ff419afb034f9509eaa0898c3467571e32d8")
        self.assertEqual(len(contract["frozen_parent_file_sha256"]), 95)
        self.assertFalse(contract["continuous_account_order_integration_verified"])

    def test_all_original_slots_and_unavailable_references_unchanged(self):
        bundle = {name: json.loads(raw) for name, raw in m.build_bundle(ROOT).items()}
        mapping = bundle["continuity-dependencies.json"]
        parent = m.frozen(ROOT / m.parent.OUTPUT_PATH / "account-state-dependencies.json")
        self.assertEqual(mapping["slots"], parent["slots"])
        self.assertEqual(mapping["session_count"], 360)
        self.assertEqual(mapping["previous_close_dependencies"], 348)
        self.assertEqual(sum(len(s["opportunity_inputs"]) for s in mapping["slots"]), 744)
        self.assertEqual(sum(r["input_status"] == "unavailable" for s in mapping["slots"] for r in s["opportunity_inputs"]), 162)

    def test_metadata_build_cannot_run_mechanics_or_open_market_bundle(self):
        with patch.object(m, "replay_path", side_effect=AssertionError("no runtime")), patch.object(m.feedback.parent.inputs, "ManagementInputBundle", side_effect=AssertionError("no tapes")):
            self.assertEqual(len(m.build_bundle(ROOT)), 4)

    def test_parent_and_implementation_mutations_fail_registration(self):
        original = m.file_sha
        for name in (m.valuation.MODULE_PATH, m.MODULE_PATH):
            with patch.object(m, "file_sha", side_effect=lambda p, n=name: "0" * 64 if str(p).endswith(n) else original(p)):
                with self.assertRaises(ValueError): m.validate_registration(ROOT)

    def test_write_once_rehashed_metadata_and_extra_files_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "bundle"
            self.assertTrue(m.write_bundle(ROOT, out)["verification_passed"])
            with self.assertRaises(FileExistsError): m.write_bundle(ROOT, out)
            path = out / "readiness-report.json"
            value = json.loads(path.read_text()); value["historical_execution_count"] = 1
            path.write_bytes(m.fees.encoded(reseal(value)))
            with self.assertRaisesRegex(ValueError, "reconstruction differs"): m.verify_bundle(ROOT, out)
            (out / "extra").write_text("x")
            with self.assertRaisesRegex(ValueError, "inventory differs"): m.verify_bundle(ROOT, out)

    def test_symlink_and_frozen_output_paths_rejected(self):
        with self.assertRaises(ValueError): m.write_bundle(ROOT, ROOT / m.valuation.OUTPUT_PATH)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "link"; path.symlink_to(Path(tmp), target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"): m.write_bundle(ROOT, path / "out")

    def test_independent_checker_recomputes_and_rejects_rehashed_scarcity(self):
        from verify_sealed_historical_account_continuity_v01 import verify as independent, verify_events
        vectors = synthetic_vectors()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "vectors.json"
            path.write_bytes(m.fees.encoded(vectors))
            report = independent(ROOT, ROOT / m.OUTPUT_PATH, path)
            self.assertTrue(report["verification_passed"])
            self.assertEqual(report["case_count"], 26)
        case = next(v for v in vectors["vectors"] if v["name"] == "collision")
        data = deepcopy(runtime(case["result"]))
        for index, event in enumerate(data["events"]):
            if event["event_type"] == "opportunity_disposition" and event["disposition"] == "blocked_capacity":
                event["account_before"]["capacity_reserved"] = False
                data["events"][index] = reseal(event)
                break
        with self.assertRaisesRegex(ValueError, "reservation or lock"):
            verify_events(case["program"]["sessions"][0], data)

    def test_direct_offline_cli_produces_independently_verified_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, vectors = Path(tmp) / "bundle", Path(tmp) / "vectors"
            commands = [[sys.executable, m.SCRIPT_PATH, "--build", "--output-root", str(out)],
                [sys.executable, m.SCRIPT_PATH, "--verify", "--output-root", str(out)],
                [sys.executable, m.SCRIPT_PATH, "--synthetic-vectors", "--output-root", str(vectors)],
                [sys.executable, m.CHECKER_PATH, "--vectors", str(vectors / "synthetic-vectors.json"), "--output", str(vectors / "independent-verification.json")]]
            for command in commands:
                proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=90)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertTrue(json.loads((vectors / "independent-verification.json").read_text())["verification_passed"])

    def test_entrypoints_have_no_undefined_globals_and_checker_is_stdlib(self):
        import ast
        from check_recovery_entrypoints_v13 import undefined_globals
        for name in (m.MODULE_PATH, m.SCRIPT_PATH, m.CHECKER_PATH):
            self.assertEqual(undefined_globals((ROOT / name).read_text(), name), set())
        tree = ast.parse((ROOT / m.CHECKER_PATH).read_text())
        imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertFalse(any(name and name.startswith("momentumbot") for name in imports))


if __name__ == '__main__':
    unittest.main()
