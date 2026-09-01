"""Frozen historical acquisition profile covering both strategy profiles.

The general and small-account profiles remain the strategy policies.  This
module derives a separate, broader profile used only to decide which market
inputs must be acquired.  A later scanner still evaluates each candidate
against each unchanged strategy profile independently.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Mapping

from .causal_market_discovery_v03 import strategy_profile_manifest
from .models import (
    StrategyProfile,
    current_general_2026,
    current_small_account_2026,
)


HISTORICAL_PROFILE_UNION_V0_1_ID = "historical-profile-union-v0.1"
GENERAL_PROFILE_ID = "current-general-2026"
SMALL_ACCOUNT_PROFILE_ID = "current-small-account-2026"

# These fingerprints bind the two pre-existing policies.  The acquisition
# union must fail closed if either strategy profile changes; it must never
# silently turn a strategy-policy edit into a wider or narrower acquisition.
GENERAL_PROFILE_FINGERPRINT = (
    "7d15fb979701324bf862b1dc37e5f9b514dcf1ab8cf1e062ae4a60027233d4ff"
)
SMALL_ACCOUNT_PROFILE_FINGERPRINT = (
    "fb86fc5326903cab16c283a03d8e371f66487f41589fb1b69b79f8912a0a6489"
)
SMALL_PROFILE_FINGERPRINT = SMALL_ACCOUNT_PROFILE_FINGERPRINT
HISTORICAL_PROFILE_UNION_V0_1_FINGERPRINT = (
    "3e062eb2f0d313201bf1901a81560586e3dc1b41220cbf7856b4d0c64ad66287"
)
HISTORICAL_PROFILE_UNION_FINGERPRINT = (
    HISTORICAL_PROFILE_UNION_V0_1_FINGERPRINT
)

_EXPECTED_PARENT_FINGERPRINTS = {
    GENERAL_PROFILE_ID: GENERAL_PROFILE_FINGERPRINT,
    SMALL_ACCOUNT_PROFILE_ID: SMALL_ACCOUNT_PROFILE_FINGERPRINT,
}
_FIXED_UNION_FIELDS: Mapping[str, object] = {
    "name": HISTORICAL_PROFILE_UNION_V0_1_ID,
    "min_price": 1.50,
    "max_price": 20.0,
    "preferred_min_price": 1.50,
    "preferred_max_price": 20.0,
    "min_percent_gain": 10.0,
    "min_relative_volume": 5.0,
    "max_float_shares": 10_000_000,
    "require_top_gainer_rank": None,
}


def _profile_fingerprint(profile: StrategyProfile) -> str:
    return str(strategy_profile_manifest(profile)["fingerprint"])


def _validate_frozen_parent(profile: StrategyProfile) -> str:
    expected = _EXPECTED_PARENT_FINGERPRINTS.get(profile.name)
    if expected is None:
        raise ValueError("historical profile union received an unknown parent profile")
    observed = _profile_fingerprint(profile)
    if observed != expected:
        raise ValueError(f"frozen strategy profile changed: {profile.name}")
    return observed


def profile_union_coverage_failures(
    acquisition_profile: StrategyProfile,
    strategy_profile: StrategyProfile,
) -> tuple[str, ...]:
    """Return acquisition predicates that fail to cover a strategy profile."""

    failures: list[str] = []
    if acquisition_profile.min_price > strategy_profile.min_price:
        failures.append("minimum price")
    if acquisition_profile.max_price < strategy_profile.max_price:
        failures.append("maximum price")
    if acquisition_profile.preferred_min_price > strategy_profile.preferred_min_price:
        failures.append("preferred minimum price")
    if acquisition_profile.preferred_max_price < strategy_profile.preferred_max_price:
        failures.append("preferred maximum price")
    if acquisition_profile.min_percent_gain > strategy_profile.min_percent_gain:
        failures.append("minimum percentage gain")
    if acquisition_profile.min_relative_volume > strategy_profile.min_relative_volume:
        failures.append("minimum relative volume")
    if acquisition_profile.max_float_shares < strategy_profile.max_float_shares:
        failures.append("maximum float")
    if acquisition_profile.require_top_gainer_rank is not None:
        failures.append("top-gainer rank prefilter")
    if acquisition_profile.volume_feature_start != strategy_profile.volume_feature_start:
        failures.append("volume feature start")
    if acquisition_profile.rvol_lookback_sessions != strategy_profile.rvol_lookback_sessions:
        failures.append("RVOL lookback")
    if acquisition_profile.session_start != strategy_profile.session_start:
        failures.append("session start")
    if acquisition_profile.no_new_entries_after != strategy_profile.no_new_entries_after:
        failures.append("entry cutoff")
    return tuple(failures)


def profile_union_covers(
    acquisition_profile: StrategyProfile,
    strategy_profile: StrategyProfile,
) -> bool:
    """Return whether acquisition is a threshold/time superset of strategy."""

    return not profile_union_coverage_failures(acquisition_profile, strategy_profile)


def derive_historical_profile_union_v0_1(
    general: StrategyProfile,
    small_account: StrategyProfile,
) -> StrategyProfile:
    """Derive and validate the fixed union from the two immutable parents."""

    before = {
        general.name: _validate_frozen_parent(general),
        small_account.name: _validate_frozen_parent(small_account),
    }
    if set(before) != set(_EXPECTED_PARENT_FINGERPRINTS):
        raise ValueError("historical profile union requires both frozen parents")

    union = replace(
        general,
        name=HISTORICAL_PROFILE_UNION_V0_1_ID,
        min_price=min(general.min_price, small_account.min_price),
        max_price=max(general.max_price, small_account.max_price),
        preferred_min_price=min(
            general.min_price,
            small_account.min_price,
        ),
        preferred_max_price=max(
            general.max_price,
            small_account.max_price,
        ),
        min_percent_gain=min(
            general.min_percent_gain,
            small_account.min_percent_gain,
        ),
        min_relative_volume=min(
            general.min_relative_volume,
            small_account.min_relative_volume,
        ),
        max_float_shares=max(
            general.max_float_shares,
            small_account.max_float_shares,
        ),
        require_top_gainer_rank=None,
    )
    for field, expected in _FIXED_UNION_FIELDS.items():
        if getattr(union, field) != expected:
            raise ValueError(f"historical profile union {field} changed")
    if _profile_fingerprint(union) != HISTORICAL_PROFILE_UNION_V0_1_FINGERPRINT:
        raise ValueError("historical profile union fingerprint changed")
    for parent in (general, small_account):
        failures = profile_union_coverage_failures(union, parent)
        if failures:
            raise ValueError(
                f"historical profile union does not cover {parent.name}: "
                + ", ".join(failures)
            )

    # StrategyProfile is frozen, but rechecking the fingerprints makes the
    # non-mutation claim explicit and independently testable.
    after = {
        general.name: _profile_fingerprint(general),
        small_account.name: _profile_fingerprint(small_account),
    }
    if after != before:
        raise RuntimeError("historical profile union altered a parent profile")
    return union


def historical_profile_union_v0_1() -> StrategyProfile:
    """Return the registered acquisition-only profile union."""

    return derive_historical_profile_union_v0_1(
        current_general_2026(),
        current_small_account_2026(),
    )


def validate_historical_profile_union_v0_1(profile: StrategyProfile) -> None:
    """Fail closed unless ``profile`` is exactly the registered union."""

    expected = historical_profile_union_v0_1()
    if strategy_profile_manifest(profile) != strategy_profile_manifest(expected):
        raise ValueError("historical acquisition profile is not the frozen union")


def historical_profile_union_v0_1_manifest() -> dict[str, object]:
    """Describe the immutable parents, derivation, and coverage guarantee."""

    general = current_general_2026()
    small = current_small_account_2026()
    union = derive_historical_profile_union_v0_1(general, small)
    return {
        "schema_version": 1,
        "profile_union_id": HISTORICAL_PROFILE_UNION_V0_1_ID,
        "purpose": "acquisition_superset_only_strategy_profiles_unchanged",
        "source_profiles": {
            GENERAL_PROFILE_ID: strategy_profile_manifest(general),
            SMALL_ACCOUNT_PROFILE_ID: strategy_profile_manifest(small),
        },
        "acquisition_profile": strategy_profile_manifest(union),
        "derivation": {
            "minimum_price": "minimum_of_source_profile_minima",
            "maximum_price": "maximum_of_source_profile_maxima",
            "minimum_percent_gain": "minimum_of_source_profile_minima",
            "minimum_relative_volume": "minimum_of_source_profile_minima",
            "maximum_float_shares": "maximum_of_source_profile_maxima",
            "top_gainer_rank": "not_applied_during_acquisition",
        },
        "coverage": {
            GENERAL_PROFILE_ID: profile_union_covers(union, general),
            SMALL_ACCOUNT_PROFILE_ID: profile_union_covers(union, small),
        },
        "strategy_profiles_modified": False,
    }
