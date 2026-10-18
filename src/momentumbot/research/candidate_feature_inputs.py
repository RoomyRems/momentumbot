"""Join accepted partial scanner inputs without promoting scanner readiness."""
from fractions import Fraction
import gzip
import math
from pathlib import Path

import pandas as pd

from momentumbot.research import candidate_daily_source as daily
from momentumbot.research import candidate_rvol_exact_source as rvol

require, exact, seal = daily.require, daily.exact, daily.seal
ID = 'early-pullback-candidate-feature-inputs-v0.1'
DAILY_PIN = {'bytes': 166974, 'sha256': '41be56526b97979434fdea382c365bec15845fb706ededfcf86a80336d5d88bd'}
RVOL_PIN = {'bytes': 28775, 'sha256': 'db8f07bde2e545fa9c8a2308ce1c5545658e3b196e9a0706ab9942cb3b506117'}


def read_pinned(path, pin):
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)),
            'regular source evidence required')
    data = path.read_bytes()
    exact({'bytes': len(data), 'sha256': daily.sha(data)}, pin, 'accepted evidence bytes differ')
    value = daily.parse(gzip.decompress(data) if path.suffix == '.gz' else data)
    daily.capture.c.d.base.verify_seal(value)
    return value


def indexed(rows, key):
    result = {row[key]: row for row in rows}
    require(len(result) == len(rows), 'duplicate source key')
    return result


def decode_curve(rows, target):
    """Keep undefined/infinite values and original bar-start timestamps."""
    stamps, values = [], []
    for stamp, value in rows:
        time = pd.Timestamp(stamp)
        require(time.tzinfo is not None, 'aware RVOL timestamp required')
        local = time.tz_convert(daily.capture.daily.ET)
        require(local.date().isoformat() == target and 4 <= local.hour < 10 and
                local.second == local.microsecond == local.nanosecond == 0,
                'RVOL timestamp outside captured minute window')
        if value is None: number = math.nan
        elif value == 'positive_infinity': number = math.inf
        else:
            require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
                    'invalid RVOL value')
            number = float(value)
        stamps.append(time); values.append(number)
    index = pd.DatetimeIndex(pd.to_datetime(stamps, utc=True))
    require(index.is_unique and index.is_monotonic_increasing, 'ordered unique RVOL times required')
    return pd.Series(values, index=index, dtype=float)


def completed_curve(curve, decision_time):
    """A bar-start observation becomes usable after its full minute closes."""
    stamp = pd.Timestamp(decision_time)
    require(stamp.tzinfo is not None, 'aware decision time required')
    require(isinstance(curve.index, pd.DatetimeIndex) and curve.index.tz is not None and
            curve.index.is_unique and curve.index.is_monotonic_increasing,
            'ordered aware RVOL curve required')
    return curve.loc[curve.index + pd.Timedelta(minutes=1) <= stamp].copy()


class CandidateFeatureInputs:
    """Read immutable accepted products; no credentials or market-data client."""
    def __init__(self, root):
        self.root = Path(root)
        daily_report = read_pinned(self.root / daily.BASE / 'audit/daily-source-audit.json.gz', DAILY_PIN)
        report = read_pinned(self.root / rvol.BASE / 'integration/integration-report.json', RVOL_PIN)
        self.daily_days = indexed(daily_report['days'], 'trading_date')
        self.rvol_days = indexed(report['days'], 'trading_date')
        exact(sorted(self.daily_days), sorted(self.rvol_days), 'source date union differs')
        self.dates = tuple(sorted(self.daily_days))
        self.source_hashes = {'daily_input_report': daily_report['content_sha256'],
                              'exact_rvol_report': report['content_sha256']}

    def read_day(self, target):
        require(target in self.daily_days, 'date outside source panel')
        meta = self.rvol_days[target]
        exact(meta['file'], target + '.json.gz', 'dated RVOL filename differs')
        evidence = read_pinned(self.root / rvol.BASE / 'integration' / meta['file'],
                               {'bytes': meta['bytes'], 'sha256': meta['sha256']})
        exact(evidence['content_sha256'], meta['content_sha256'], 'dated RVOL seal differs')
        exact(evidence['trading_date'], target, 'RVOL date differs')
        cases = indexed(evidence['cases'], 'symbol')
        histories = indexed(self.daily_days[target]['cases'], 'symbol')
        require(set(cases) <= set(histories), 'RVOL candidate outside daily population')
        curves = evidence['candidate_exact_rvol_by_symbol']
        exact(sorted(curves), sorted(s for s, c in cases.items() if c['status'] == 'exact_rvol_ready'),
              'ready RVOL curve union differs')
        features, decoded = {}, {}
        for symbol, history in sorted(histories.items()):
            comparison = history['previous_close_comparison']
            close = (float(Fraction(comparison['saved_close']))
                     if comparison['status'] == 'previous_close_matches' else None)
            status = cases[symbol]['status'] if symbol in cases else 'not_retained_for_exact_capture'
            if symbol in curves:
                decoded[symbol] = decode_curve(curves[symbol], target)
                exact(len(decoded[symbol]), cases[symbol]['rvol_observations'], 'RVOL count differs')
            features[symbol] = {'previous_close': close,
                'average_daily_volume_50': history['average_daily_volume_50'],
                'daily_history_sufficient': history['sufficient_history'], 'exact_rvol_status': status}
        provenance = seal({'contract_id': ID, 'trading_date': target,
            'source_hashes': self.source_hashes, 'dated_rvol_sha256': evidence['content_sha256'],
            'candidate_count': len(features), 'exact_curve_count': len(decoded),
            'timestamp_semantics': 'bar start; available at bar start plus one minute',
            'full_scanner_inputs_complete': False, 'float_news_integrated': False, **daily.BOUNDARY})
        return {'trading_date': target, 'features_by_symbol': features,
                'candidate_exact_rvol_by_symbol': decoded, 'provenance': provenance}
