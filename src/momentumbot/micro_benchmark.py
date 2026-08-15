"""Post-replay comparison against retrospective micro-trade labels.

This module sits *after* causal runtime reconstruction. It accepts a serialized
runtime replay artifact and a retrospective benchmark label, validates that the
runtime artifact was produced under the no-label knowledge policy, and reports
field-level agreement or disagreement.

It intentionally does not produce a weighted imitation score, choose a strategy
variant, or modify any replay input. Benchmark labels are evaluation data only.
"""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral, Real
from typing import Mapping, Sequence

RUNTIME_KNOWLEDGE_POLICY = "runtime_market_data_only_no_retrospective_labels"
LABEL_KNOWLEDGE_POLICY = "ground_truth_label_only_never_runtime_context"


@dataclass(frozen=True, slots=True)
class MicroBenchmarkComparison:
    benchmark_id: str
    symbol: str
    runtime_policy_name: str
    observed_setup_type: str | None
    setup_family_match: bool | None
    runtime_filled_pullback_numbers: tuple[int, ...]
    observed_pullback_ordinal: int | None
    first_runtime_filled_pullback_number: int | None
    pullback_ordinal_match: bool | None
    runtime_first_pullback_filled: bool
    observed_first_pullback_taken: bool | None
    first_pullback_taken_match: bool | None
    runtime_plan_trigger_prices: tuple[float, ...]
    runtime_filled_trigger_prices: tuple[float, ...]
    observed_trigger_references: tuple[float, ...]
    trigger_reference_absolute_differences: tuple[tuple[float, ...], ...]
    runtime_fill_prices: tuple[float, ...]
    reported_fill_references: tuple[float, ...]
    fill_absolute_differences: tuple[tuple[float, ...], ...]

    @property
    def comparable_fields(self) -> int:
        values = (
            self.setup_family_match,
            self.pullback_ordinal_match,
            self.first_pullback_taken_match,
        )
        return sum(value is not None for value in values)

    @property
    def matching_fields(self) -> int:
        values = (
            self.setup_family_match,
            self.pullback_ordinal_match,
            self.first_pullback_taken_match,
        )
        return sum(value is True for value in values)


def _as_mapping(value: object, *, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    return value


def _numeric(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    return float(value)


def _numeric_sequence(value: object) -> tuple[float, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return ()
    output: list[float] = []
    for item in value:
        numeric = _numeric(item)
        if numeric is not None:
            output.append(numeric)
    return tuple(output)


def _reported_fill_references(observed: Mapping[str, object]) -> tuple[float, ...]:
    values: list[float] = []
    for key in ("reported_fill_approx",):
        numeric = _numeric(observed.get(key))
        if numeric is not None:
            values.append(numeric)
    for key in ("reported_entry_fills_approx", "reported_entry_fills"):
        values.extend(_numeric_sequence(observed.get(key)))
    return tuple(values)


def _observed_trigger_references(observed: Mapping[str, object]) -> tuple[float, ...]:
    values: list[float] = []
    for key in (
        "intended_break_level",
        "reported_confirmation_level",
        "reported_second_pullback_add_break_level",
    ):
        numeric = _numeric(observed.get(key))
        if numeric is not None:
            values.append(numeric)
    return tuple(values)


def _runtime_steps(runtime: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    raw = runtime.get("steps")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise ValueError("runtime artifact steps must be a sequence")
    return tuple(_as_mapping(step, name="runtime step") for step in raw)


def _runtime_prices(
    steps: tuple[Mapping[str, object], ...],
    *,
    filled_only: bool,
    source: str,
    field: str,
) -> tuple[float, ...]:
    output: list[float] = []
    for step in steps:
        outcome_raw = step.get("outcome")
        outcome = outcome_raw if isinstance(outcome_raw, Mapping) else None
        if filled_only:
            fill = _numeric(outcome.get("fill_price")) if outcome is not None else None
            if fill is None:
                continue
        source_raw = step.get(source)
        source_mapping = source_raw if isinstance(source_raw, Mapping) else None
        if source_mapping is None:
            continue
        numeric = _numeric(source_mapping.get(field))
        if numeric is not None:
            output.append(numeric)
    return tuple(output)


def _runtime_fill_prices(steps: tuple[Mapping[str, object], ...]) -> tuple[float, ...]:
    output: list[float] = []
    for step in steps:
        outcome_raw = step.get("outcome")
        if not isinstance(outcome_raw, Mapping):
            continue
        numeric = _numeric(outcome_raw.get("fill_price"))
        if numeric is not None:
            output.append(numeric)
    return tuple(output)


def _absolute_difference_matrix(
    runtime_values: tuple[float, ...],
    observed_values: tuple[float, ...],
) -> tuple[tuple[float, ...], ...]:
    return tuple(
        tuple(abs(runtime_value - observed_value) for observed_value in observed_values)
        for runtime_value in runtime_values
    )


def compare_micro_runtime_to_label(
    runtime_artifact: Mapping[str, object],
    benchmark_label: Mapping[str, object],
) -> MicroBenchmarkComparison:
    """Compare a completed runtime artifact to a retrospective label.

    The function is descriptive only. Price differences are returned as full
    pairwise matrices so callers do not silently select whichever runtime plan
    happens to be nearest to a reported fill or trigger.
    """
    runtime = _as_mapping(runtime_artifact, name="runtime_artifact")
    label = _as_mapping(benchmark_label, name="benchmark_label")
    if runtime.get("artifact_type") != "micro_candidate_runtime_replay":
        raise ValueError("unexpected runtime artifact type")
    if runtime.get("knowledge_policy") != RUNTIME_KNOWLEDGE_POLICY:
        raise ValueError("runtime artifact does not satisfy the no-label knowledge policy")
    if label.get("knowledge_policy") != LABEL_KNOWLEDGE_POLICY:
        raise ValueError("benchmark label is not marked retrospective ground truth")

    runtime_symbol = str(runtime.get("symbol") or "")
    label_symbol = str(label.get("symbol") or "")
    if not runtime_symbol or runtime_symbol != label_symbol:
        raise ValueError("runtime and benchmark symbols must match")

    observed = _as_mapping(label.get("observed_human_behavior"), name="observed_human_behavior")
    steps = _runtime_steps(runtime)
    raw_filled_numbers = runtime.get("filled_pullback_numbers", ())
    if not isinstance(raw_filled_numbers, Sequence) or isinstance(raw_filled_numbers, (str, bytes)):
        raise ValueError("runtime filled_pullback_numbers must be a sequence")
    filled_numbers = tuple(
        int(value)
        for value in raw_filled_numbers
        if isinstance(value, Integral) and not isinstance(value, bool)
    )
    first_filled_number = filled_numbers[0] if filled_numbers else None

    observed_ordinal_raw = observed.get("pullback_ordinal")
    observed_ordinal = (
        int(observed_ordinal_raw)
        if isinstance(observed_ordinal_raw, Integral) and not isinstance(observed_ordinal_raw, bool)
        else None
    )
    ordinal_match = (
        first_filled_number == observed_ordinal
        if observed_ordinal is not None and first_filled_number is not None
        else None
    )

    first_pullback_filled = 1 in filled_numbers
    observed_first_taken_raw = observed.get("first_pullback_taken")
    observed_first_taken = (
        bool(observed_first_taken_raw)
        if isinstance(observed_first_taken_raw, bool)
        else None
    )
    first_taken_match = (
        first_pullback_filled == observed_first_taken
        if observed_first_taken is not None
        else None
    )

    setup_raw = observed.get("setup_type")
    observed_setup = str(setup_raw) if isinstance(setup_raw, str) else None
    setup_match = (
        observed_setup == "micro_pullback" if observed_setup is not None else None
    )

    plan_triggers = _runtime_prices(
        steps,
        filled_only=False,
        source="plan",
        field="minimum_new_high_price",
    )
    filled_triggers = _runtime_prices(
        steps,
        filled_only=True,
        source="plan",
        field="minimum_new_high_price",
    )
    observed_triggers = _observed_trigger_references(observed)
    runtime_fills = _runtime_fill_prices(steps)
    reported_fills = _reported_fill_references(observed)

    return MicroBenchmarkComparison(
        benchmark_id=str(label.get("benchmark_id") or ""),
        symbol=runtime_symbol,
        runtime_policy_name=str(runtime.get("policy_name") or ""),
        observed_setup_type=observed_setup,
        setup_family_match=setup_match,
        runtime_filled_pullback_numbers=filled_numbers,
        observed_pullback_ordinal=observed_ordinal,
        first_runtime_filled_pullback_number=first_filled_number,
        pullback_ordinal_match=ordinal_match,
        runtime_first_pullback_filled=first_pullback_filled,
        observed_first_pullback_taken=observed_first_taken,
        first_pullback_taken_match=first_taken_match,
        runtime_plan_trigger_prices=plan_triggers,
        runtime_filled_trigger_prices=filled_triggers,
        observed_trigger_references=observed_triggers,
        trigger_reference_absolute_differences=_absolute_difference_matrix(
            plan_triggers, observed_triggers
        ),
        runtime_fill_prices=runtime_fills,
        reported_fill_references=reported_fills,
        fill_absolute_differences=_absolute_difference_matrix(
            runtime_fills, reported_fills
        ),
    )
