# Catalyst interpretation protocol v0.2

Status: **shadow research protocol; no trading authority**.

## Why this exists

Ross does not treat every headline—or the absence of a headline—the same way. The ARTL and ZEVAI transcripts make four distinctions explicit:

1. **Commitment stage.** A board approving the pursuit of an investment is not the same as a signed, announced or completed transaction.
2. **Quantified economics.** An announced ~$400M stake contains more concrete information than an unquantified proposal, although the amount alone still does not prove materiality.
3. **Repetition.** Reusing similar promotional language can reduce trust; one current headline cannot prove novelty without a reliable prior-event corpus.
4. **Offering overhang.** Starting or pricing an offering can increase dilution concern, while withdrawing a contemplated offering can reduce the immediate overhang.

The frozen v0.1 protocol could not represent these distinctions. v0.2 adds them as structured observations.

## What it records

For a headline already available in the causal evidence packet, a shadow interpreter may record:

- whether the title describes exploration, board authorization, a definitive/completed action, or withdrawal/cancellation;
- whether the title contains a specific economic amount, only unrelated numeric terms, or no economic amount;
- whether at least two already-available packet headlines look potentially repetitive;
- whether the title explicitly signals an offering/dilution event or withdrawal of that overhang.

Every non-ambiguous claim requires a matching observation code and an available headline ID. Possible repetition requires at least two cited packet headlines.

## What it deliberately cannot say

The protocol does not output a catalyst score, candidate rank, trade recommendation, order, position size or risk change. It also keeps these fields unknown:

- true novelty without a complete causal prior-event corpus;
- economic materiality from a title alone;
- theme fit without a frozen causal theme state.

Even a title containing a dollar amount cannot be labeled materially important without company-relative terms and corroborating evidence. Likewise, not seeing a similar prior title is not proof that an event is new.

## Research use

v0.2 is the vocabulary and validation boundary for a later shadow-only interpreter. It is not that interpreter and is not a strategy rule. The next legitimate test is a chronological held-out panel containing both trades and skips, with the exact title, article or filing available by each simulated decision time.

The machine-readable contract is `research/strategy/catalyst-interpretation-protocol-shadow-v0.2.json`; the validation decision is recorded in `research/data-audits/catalyst-interpretation-protocol-shadow-v0.2.json`.
