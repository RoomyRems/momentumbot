# Residual cancellation-status verification v0.1

This separately registered verifier checks the exact runtime preserved by the
failed residual replay. It corrects one known checker defect: zero-fill
cancellations must distinguish a missing fresh quote, halted quotes, and an
ordinary unfilled order. The correction uses the original native quote/status
lifecycle. All other frozen verification predicates remain unchanged.

## Immutable parents and registration

The diagnosis checkpoint is `89c83f04de92cff6d7ce8d38ee30b9b280dabf56`, tree
`334eadc8380301f613945c1d6a8a35e4bbcfa121`.
The consumed residual producer and failed checker remain at implementation
`49e35b57f06b97a73590517b993de0e333d692dd`, registration
`33ced4d6e2069f36a277b3b2025f38e07e2d7a3e9eeecd031345400ed6b54dae`.
Their files and failure are retained without edits.

The child contract is
`sealed-historical-account-residual-exit-status-verification-v0.1`.
Its registration freeze is
`ed0f19906970ed71af17bf32cbd72ebe2284daa8ad59f80557257035a5f85f85`;
contract content SHA is
`16d1658aff06bfae25a8206b37cbbd35ef9031fdabf51595668e9e1e5e803318`.
It preserves all 270 original file pins, adding the original registration and
published diagnosis for 278 parent pins, plus three child implementation pins.
This registration is explicitly informed by the known prior failure. It must be
published before the corrected checker is applied to historical runtime bytes.

The fixed input runtime has content SHA
`21bd9efa65c5c5776242bb9a6a53d28c134aefe31ed7da00d389402e29f3efba`
and file SHA
`90f5a02dacc26eec03e8aacb5758150c0efc8b6a9b56d9c1d4eb7f5d7287c716`.
It comes only from failed run `34295994393`, artifact `10085178783`.
The registration commits exact bytes and hashes for that ZIP, the original
binding ZIP, verified waiting-parent ZIP, management ZIP and exit-input ZIP.
The mandatory population remains 12 paths, 360 session slots, 744 opportunity
references and 162 unavailable references.

## Exact correction

| Confirmed fills / original active quote evidence | Expected cancellation status |
|---|---|
| Positive confirmed filled quantity, with a cancelled remainder | `partially_filled_cancelled` |
| Zero fills; no fresh active quote candidates | `unavailable_no_fresh_quote` |
| Zero fills; every active candidate halted | `halted_cancelled` |
| Zero fills; at least one active candidate trading | `cancelled_unfilled` |

The zero-fill classification uses the separately published, pinned
`quote_lifecycle` implementation from the failure diagnostic. It checks frozen
policy clocks, original capture coverage, known status, valid quote fields,
quote age at arrival, inclusive arrival and exclusive cancellation
acknowledgement. There is no unchecked status allowlist.

The child explicitly copies the original residual verification function with
one expected-status expression changed. It copies the outer original verifier
with only its function name changed. AST parity tests enforce both limits.
Accounting, chronology, exact decimal risk, source identity, waiting, original
parent event prefixes, quantities, cancellation clocks, liquidity identity,
residual authority and the two-terminal-order ceiling retain the original
functions and predicates. The producer and runtime are never patched.

This classifies recorded cancellation outcomes. It is not a second independent
fill simulator, a new execution assumption, or a policy promotion.

## Validation and attempt handling

Sixteen new synthetic tests cover both frozen execution scenarios, valid
no-quote and halted feedback, ordinary unfilled and partial cancellations,
delayed submission, expiration and exhausted residuals. They reject rehashed
forged statuses, missing authority, changed shares, unknown status, changed
clocks, invalid source coverage, wrong registrations and a different runtime.
They verify source-expression parity and durable success/failure receipts.

All 62 focused tests passed normally (12.531 seconds) and with Python
optimization (12.696 seconds), zero skips. All 2,315 local tests passed with
zero skips in 278.291 seconds on Python 3.12.13 before publication. The original
failure regression remains a passing test of the retained defect. Exact log
hashes and validation evidence are recorded in the
[registration audit](../../research/data-audits/sealed-historical-account-residual-exit-status-verification-v0.1-registration.json),
content SHA `b1ded43c954ff69d22a55f9a8c0aeb84b6cb1e8e404ddbd39746ef9b6147364d`.

The offline CLI requires an externally supplied registration freeze and a new
output directory. It writes a sealed attempt receipt before reading historical
inputs. Success emits a distinct child verification report and byte inventory;
failure emits a sealed failure record and retains the receipt. Existing output
directories cannot be reused. The CLI denies network and subprocess access.

The hosted workflow downloads only the five immutable GitHub artifacts, checks
their byte commitments, and verifies the saved runtime once. It never starts the
account replay. Its report is a child artifact, not a replacement for the absent
original independent report. Local and hosted child output must be compared
directly, including byte identities and inventory, before recording acceptance.
Any additional failure must remain attached to this frozen verifier version.

## Remaining boundary

Before execution, complete runtime acceptance remains unestablished. Even if
the corrected checks pass, checking one stored runtime in two environments does
not reproduce the account replay. The original local attempt still has no
runtime output and must remain documented separately. Any fresh account replay
requires a separately recorded reproduction attempt.

Financial evaluation, account-backtest completion, retrospective labels,
overnight execution and promotion remain closed. No market-provider request or
broker action is authorized. Ross attachments remain unopened.

See the [preserved source diagnosis](sealed_historical_account_residual_exit_cancellation_diagnostic_v01.md)
and [current checkpoint](../project/current_state_2026-08-31.md).
