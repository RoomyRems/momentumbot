from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Mapping, Sequence

from momentumbot.identity_resolved_universe import json_fingerprint
from momentumbot.micro_policy import micro_v0_1_policy
from momentumbot.research.discretion_heldout_panel import REGISTERED_DATES


DATE_ARTIFACT_ID = "ross-discretion-heldout-micro-date-runtime-v0.1"
PANEL_ARTIFACT_ID = "ross-discretion-heldout-micro-runtime-v0.1"
SOURCE_MANIFEST_CONTENT_SHA256 = (
    "2414f7389bf68d5a5e4b3302c646c9111020cb79ce06fc0213f7872062f79c48"
)
FROZEN_MICRO_POLICY_FINGERPRINT = (
    "49c27b4a1925da4990095e6ffb82bf7557743d1b58ea38f20eee69bce62618fa"
)
_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_INPUT_KEYS = {
    "trades",
    "bars_10s",
    "support",
    "session_1m",
    "ema_warmup_1m",
}


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _validated_fingerprint(
    payload: Mapping[str, object], *, description: str
) -> str:
    claimed = payload.get("content_sha256")
    if not isinstance(claimed, str) or not _SHA256.fullmatch(claimed):
        raise ValueError(f"{description} lacks a valid content fingerprint")
    projection = {
        key: value for key, value in payload.items() if key != "content_sha256"
    }
    if claimed != json_fingerprint(projection):
        raise ValueError(f"{description} fingerprint mismatch")
    return claimed


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _count(value: object, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _validate_input_files(symbol_root: Path, payload: Mapping[str, object]) -> None:
    inputs = payload.get("input_files")
    if not isinstance(inputs, Mapping) or set(inputs) != _INPUT_KEYS:
        raise ValueError("replayed runtime has incomplete frozen input files")
    seen: set[str] = set()
    for name, raw in inputs.items():
        if not isinstance(raw, Mapping):
            raise ValueError(f"invalid input metadata for {name}")
        filename = raw.get("path")
        claimed = raw.get("sha256")
        _count(raw.get("row_count"), name=f"{name} row_count")
        if (
            not isinstance(filename, str)
            or Path(filename).name != filename
            or filename in seen
        ):
            raise ValueError(f"unsafe or duplicate input filename for {name}")
        if not isinstance(claimed, str) or not _SHA256.fullmatch(claimed):
            raise ValueError(f"invalid input hash for {name}")
        path = symbol_root / filename
        if not path.is_file() or _sha256(path) != claimed:
            raise ValueError(f"frozen input file mismatch for {name}")
        seen.add(filename)


def _validate_runtime(
    *,
    symbol_root: Path,
    symbol: str,
    trading_date: str,
    candidate_result: Mapping[str, object],
    policy_id: str,
    policy_fingerprint: str,
) -> dict[str, object]:
    runtime_path = symbol_root / "runtime-replay.json"
    runtime = _read_json(runtime_path)
    claimed = _validated_fingerprint(
        runtime, description=f"{trading_date}/{symbol} runtime"
    )
    if claimed != candidate_result.get("runtime_content_sha256"):
        raise ValueError("candidate result does not bind its runtime")
    if runtime.get("symbol") != symbol or runtime.get("trading_date") != trading_date:
        raise ValueError("micro runtime symbol/date mismatch")
    if runtime.get("candidate_qualified_at") != candidate_result.get(
        "candidate_qualified_at"
    ):
        raise ValueError("micro runtime activation mismatch")
    if (
        runtime.get("frozen_policy_id") != policy_id
        or runtime.get("frozen_policy_fingerprint") != policy_fingerprint
    ):
        raise ValueError("micro runtime policy mismatch")
    source_hashes = runtime.get("source_hashes")
    if not isinstance(source_hashes, Mapping) or source_hashes.get(
        "heldout_runtime"
    ) != SOURCE_MANIFEST_CONTENT_SHA256:
        raise ValueError("micro runtime source mismatch")

    artifact_type = runtime.get("artifact_type")
    if artifact_type == "micro_candidate_runtime_replay":
        if candidate_result.get("status") != "replayed":
            raise ValueError("replayed runtime has inconsistent status")
        plans = _count(runtime.get("plan_count"), name="runtime plan_count")
        fills = _count(runtime.get("filled_count"), name="runtime filled_count")
        if fills > plans:
            raise ValueError("micro runtime has more fills than plans")
        if runtime.get("retrospective_behavior_labels_loaded") is not False:
            raise ValueError("micro runtime opened retrospective labels")
        _validate_input_files(symbol_root, runtime)
    elif artifact_type == "micro_candidate_runtime_replay_unavailable":
        if runtime.get("plan_count") is not None or runtime.get("filled_count") is not None:
            raise ValueError("unavailable runtime must not masquerade as zero activity")
        if candidate_result.get("status") != runtime.get("status"):
            raise ValueError("unavailable runtime has inconsistent status")
        plans = None
        fills = None
    else:
        raise ValueError("unexpected micro runtime artifact type")

    if plans != candidate_result.get("plan_count") or fills != candidate_result.get(
        "filled_count"
    ):
        raise ValueError("candidate result activity differs from runtime")
    return {
        "symbol": symbol,
        "trading_date": trading_date,
        "status": candidate_result["status"],
        "candidate_qualified_at": candidate_result["candidate_qualified_at"],
        "plan_count": plans,
        "filled_count": fills,
        "runtime_content_sha256": claimed,
    }


def _validate_date(
    root: Path,
    trading_date: str,
    *,
    policy_id: str,
    policy_fingerprint: str,
    policy_status: str,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    manifest = _read_json(root / trading_date / "manifest.json")
    manifest_hash = _validated_fingerprint(
        manifest, description=f"{trading_date} date manifest"
    )
    if manifest.get("schema_version") != 1 or manifest.get(
        "artifact_id"
    ) != DATE_ARTIFACT_ID:
        raise ValueError("unexpected micro date artifact")
    if manifest.get("trading_date") != trading_date:
        raise ValueError("micro date manifest date mismatch")
    if manifest.get(
        "source_heldout_runtime_content_sha256"
    ) != SOURCE_MANIFEST_CONTENT_SHA256:
        raise ValueError("micro date manifest source mismatch")
    policy = manifest.get("frozen_micro_policy")
    if policy != {
        "policy_id": policy_id,
        "fingerprint": policy_fingerprint,
        "status": policy_status,
    }:
        raise ValueError("micro date manifest policy mismatch")
    knowledge = manifest.get("knowledge_policy")
    if not isinstance(knowledge, Mapping):
        raise ValueError("micro date manifest lacks knowledge policy")
    if knowledge.get("all_causal_market_candidates_retained") is not True:
        raise ValueError("micro date manifest omitted candidates")
    for field in (
        "uses_ross_actions",
        "uses_benchmark_labels",
        "uses_retrospective_trade_outcomes",
        "uses_later_price_outcomes",
    ):
        if knowledge.get(field) is not False:
            raise ValueError(f"micro date manifest violates {field}")
    eligibility = manifest.get("eligibility")
    if not isinstance(eligibility, Mapping) or eligibility.get(
        "policy_promotion_eligible"
    ) is not False:
        raise ValueError("micro date manifest overclaims policy eligibility")

    raw_results = manifest.get("candidate_results")
    if not isinstance(raw_results, Mapping):
        raise ValueError("micro date manifest lacks candidate results")
    symbols = sorted(str(symbol) for symbol in raw_results)
    if len(symbols) != len(set(symbols)) or any(
        not _SYMBOL.fullmatch(symbol) for symbol in symbols
    ):
        raise ValueError("micro date manifest has invalid candidate symbols")
    if _count(manifest.get("candidate_count"), name="candidate_count") != len(symbols):
        raise ValueError("micro date candidate count mismatch")

    rows: list[dict[str, object]] = []
    for symbol in symbols:
        result = raw_results[symbol]
        if not isinstance(result, Mapping):
            raise ValueError("invalid candidate result")
        rows.append(
            _validate_runtime(
                symbol_root=root / trading_date / symbol,
                symbol=symbol,
                trading_date=trading_date,
                candidate_result=result,
                policy_id=policy_id,
                policy_fingerprint=policy_fingerprint,
            )
        )

    replayed = [row for row in rows if row["status"] == "replayed"]
    unavailable = [row for row in rows if row["status"] != "replayed"]
    total_plans = sum(int(row["plan_count"]) for row in replayed)
    total_fills = sum(int(row["filled_count"]) for row in replayed)
    expected = {
        "replayed_candidate_count": len(replayed),
        "unavailable_candidate_count": len(unavailable),
        "total_plan_count": total_plans,
        "total_filled_count": total_fills,
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError("micro date totals do not reconcile")
    summary = {
        "date_manifest_content_sha256": manifest_hash,
        "candidate_count": len(rows),
        **expected,
        "candidates_with_plan": sum(int(row["plan_count"]) > 0 for row in replayed),
        "candidates_with_fill": sum(int(row["filled_count"]) > 0 for row in replayed),
        "candidates_with_zero_plans": sum(
            int(row["plan_count"]) == 0 for row in replayed
        ),
    }
    return summary, rows


def build_panel_manifest(
    input_root: Path,
    *,
    dates: Sequence[str] = REGISTERED_DATES,
) -> dict[str, object]:
    if not dates or len(dates) != len(set(dates)):
        raise ValueError("micro panel dates must be nonempty and unique")
    policy = micro_v0_1_policy()
    if policy.fingerprint != FROZEN_MICRO_POLICY_FINGERPRINT:
        raise RuntimeError("Micro v0.1 differs from its registered frozen fingerprint")
    date_results: dict[str, object] = {}
    candidates: list[dict[str, object]] = []
    for trading_date in dates:
        summary, rows = _validate_date(
            input_root,
            trading_date,
            policy_id=policy.policy_id,
            policy_fingerprint=policy.fingerprint,
            policy_status=policy.status,
        )
        date_results[trading_date] = summary
        candidates.extend(rows)

    replayed = [row for row in candidates if row["status"] == "replayed"]
    unavailable = [row for row in candidates if row["status"] != "replayed"]
    total_plans = sum(int(row["plan_count"]) for row in replayed)
    total_fills = sum(int(row["filled_count"]) for row in replayed)
    replayed_count = len(replayed)
    totals = {
        "candidate_count": len(candidates),
        "replayed_candidate_count": replayed_count,
        "unavailable_candidate_count": len(unavailable),
        "total_plan_emission_count": total_plans,
        "total_modeled_fill_count": total_fills,
        "candidates_with_plan": sum(int(row["plan_count"]) > 0 for row in replayed),
        "candidates_with_fill": sum(int(row["filled_count"]) > 0 for row in replayed),
        "candidates_with_zero_plans": sum(
            int(row["plan_count"]) == 0 for row in replayed
        ),
        "plan_emissions_per_replayed_candidate": (
            total_plans / replayed_count if replayed_count else None
        ),
        "modeled_fills_per_replayed_candidate": (
            total_fills / replayed_count if replayed_count else None
        ),
    }
    payload: dict[str, object] = {
        "schema_version": 1,
        "artifact_id": PANEL_ARTIFACT_ID,
        "dates": list(dates),
        "source_heldout_runtime_content_sha256": SOURCE_MANIFEST_CONTENT_SHA256,
        "frozen_micro_policy": {
            "policy_id": policy.policy_id,
            "fingerprint": policy.fingerprint,
            "status": policy.status,
        },
        "date_results": date_results,
        "totals": totals,
        "candidate_results": candidates,
        "knowledge_policy": {
            "uses_ross_actions": False,
            "uses_benchmark_labels": False,
            "uses_retrospective_trade_outcomes": False,
            "uses_later_price_outcomes": False,
            "all_causal_market_candidates_retained": True,
        },
        "interpretation": {
            "activity_density_descriptive_only": True,
            "plan_emission_is_not_a_portfolio_trade": True,
            "repeated_plans_may_represent_the_same_momentum_campaign": True,
            "unavailable_candidates_excluded_from_activity_denominators": True,
            "technical_rule_retuning_allowed": False,
            "human_imitation_scoring_started": False,
            "policy_promotion_eligible": False,
            "full_imitation_claim_eligible": False,
        },
        "limits": [
            "entry latency is fixed at zero milliseconds",
            "Level 2 and synchronized order-book state are absent",
            "account state, buying power, and attention allocation are absent",
            "provider dissemination latency is not modeled",
        ],
    }
    payload["content_sha256"] = json_fingerprint(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate and summarize all registered label-blind Micro v0.1 date "
            "replays without loading human labels."
        )
    )
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"output already exists: {args.output}")
    payload = build_panel_manifest(args.input_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload["totals"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
