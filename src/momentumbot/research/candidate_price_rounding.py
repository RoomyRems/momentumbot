"""Offline test of nearest-cent adjusted-price rounding, never normalization."""
from fractions import Fraction
import math
from numbers import Real

from momentumbot.research.candidate_source_archive import require

HALF_CENT = Fraction(1, 200)


def positive_decimal(value):
    require(isinstance(value, Real) and not isinstance(value, bool)
        and math.isfinite(float(value)) and value > 0, 'positive finite price required')
    return Fraction(str(value))


def nearest_cent_factor_interval(raw_price, adjusted_price):
    """Closed endpoints leave tie-breaking unspecified, without any epsilon."""
    raw, adjusted = positive_decimal(raw_price), positive_decimal(adjusted_price)
    require((adjusted * 100).denominator == 1, 'adjusted price not on cent grid')
    return (adjusted - HALF_CENT) / raw, (adjusted + HALF_CENT) / raw


def render_fraction(value):
    return {'numerator': value.numerator, 'denominator': value.denominator}


def explain_case(raw, split, *, raw_daily_high, split_daily_high, model='nearest_cent'):
    """Test one constant factor against every minute and the original daily high.

    Full-day high values belong only to this diagnostic. An interval satisfying
    this model does not authenticate the vendor's rounding algorithm, establish
    another symbol's adjustment basis, or authorize changing runtime prices.
    """
    require(model in ('nearest_cent', 'observed_precision'), 'unknown rounding model')
    daily_raw, daily_split = positive_decimal(raw_daily_high), positive_decimal(split_daily_high)
    for frame in (raw, split):
        require(frame.index.tz is not None and frame.index.is_unique and frame.index.is_monotonic_increasing,
            'unique ordered aware source times required')
    boundary = {'daily_minute_share_basis_verified': False, 'runtime_normalization_authorized': False}
    if not raw.index.equals(split.index): return {'status': 'timestamp_mismatch', **boundary}
    if raw.empty: return {'status': 'empty_pair', **boundary}
    pairs = [(positive_decimal(a), positive_decimal(b)) for a, b in zip(raw['close'], split['close'], strict=True)]
    exact_factor = daily_split / daily_raw
    if all(a * exact_factor == b for a, b in pairs):
        return {'status': 'exact_constant_factor', 'factor': render_fraction(exact_factor), **boundary}
    # This alternative is an explicitly post-hoc diagnostic of observed source
    # precision, not a vendor specification or an accepted runtime transform.
    def quantum(value):
        return Fraction(1, 1000) if model == 'observed_precision' and value < 10 else Fraction(1, 100)
    all_pairs = [(daily_raw, daily_split), *pairs]
    if any((b / quantum(b)).denominator != 1 for _, b in all_pairs):
        return {'status': 'not_on_cent_grid' if model == 'nearest_cent' else 'not_on_model_grid', **boundary}
    intervals = [((b - quantum(b) / 2) / a, (b + quantum(b) / 2) / a) for a, b in all_pairs]
    low, high = max(lo for lo, _ in intervals), min(hi for _, hi in intervals)
    if low > high:
        return {'status': 'incompatible_constant_factor', 'interval_lower': render_fraction(low),
            'interval_upper': render_fraction(high), **boundary}
    return {'status': 'compatible_nearest_cent_rounding' if model == 'nearest_cent' else 'compatible_observed_precision', 'interval_lower': render_fraction(low),
        'interval_upper': render_fraction(high), 'tie_breaking_verified': False,
        'vendor_rounding_documented': False, **boundary}
