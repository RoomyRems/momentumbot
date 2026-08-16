"""Leakage-safe benchmark-suite manifests for deterministic strategy research.

Suite manifests select retrospective benchmark labels for *post-replay*
evaluation.  They never supply labels to the runtime strategy.  The explicit
case roles prevent advanced-context or ambiguous examples from being counted
as if they were ordinary Micro v0.1 decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Any


GROUND_TRUTH_POLICY = "ground_truth_label_only_never_runtime_context"


class BenchmarkCaseRole(str, Enum):
    PRIMARY = "primary_scored"
    PARTIAL = "partial_scored"
    BOUNDARY = "boundary_context_only"
    AMBIGUOUS = "ambiguous_excluded"


@dataclass(frozen=True, slots=True)
class BenchmarkSuiteCase:
    benchmark_id: str
    benchmark_path: str
    role: BenchmarkCaseRole
    tags: tuple[str, ...]
    scored_dimensions: tuple[str, ...]
    rationale: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BenchmarkSuiteCase":
        return cls(
            benchmark_id=str(data["benchmark_id"]),
            benchmark_path=str(data["benchmark_path"]),
            role=BenchmarkCaseRole(data["role"]),
            tags=tuple(str(item) for item in data.get("tags", [])),
            scored_dimensions=tuple(
                str(item) for item in data.get("scored_dimensions", [])
            ),
            rationale=str(data["rationale"]),
        )

    def validate(self) -> None:
        if not self.benchmark_id.strip():
            raise ValueError("benchmark_id is required")
        if not self.benchmark_path.startswith("research/benchmarks/"):
            raise ValueError(
                f"benchmark path must stay under research/benchmarks: {self.benchmark_path}"
            )
        if self.role in {BenchmarkCaseRole.BOUNDARY, BenchmarkCaseRole.AMBIGUOUS}:
            if self.scored_dimensions:
                raise ValueError(
                    f"{self.role.value} case cannot have scored dimensions: {self.benchmark_id}"
                )
        elif not self.scored_dimensions:
            raise ValueError(
                f"scored case requires at least one scored dimension: {self.benchmark_id}"
            )


@dataclass(frozen=True, slots=True)
class BenchmarkSuite:
    suite_id: str
    policy_id: str
    knowledge_policy: str
    status: str
    cases: tuple[BenchmarkSuiteCase, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BenchmarkSuite":
        suite = cls(
            suite_id=str(data["suite_id"]),
            policy_id=str(data["policy_id"]),
            knowledge_policy=str(data["knowledge_policy"]),
            status=str(data["status"]),
            cases=tuple(BenchmarkSuiteCase.from_dict(item) for item in data["cases"]),
        )
        suite.validate()
        return suite

    def validate(self) -> None:
        if self.knowledge_policy != GROUND_TRUTH_POLICY:
            raise ValueError("benchmark suites must use retrospective-label-only policy")
        ids = [case.benchmark_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("benchmark suite contains duplicate benchmark IDs")
        paths = [case.benchmark_path for case in self.cases]
        if len(paths) != len(set(paths)):
            raise ValueError("benchmark suite contains duplicate benchmark paths")
        if not self.cases:
            raise ValueError("benchmark suite must contain at least one case")
        for case in self.cases:
            case.validate()

    @property
    def primary_scored_count(self) -> int:
        return sum(case.role is BenchmarkCaseRole.PRIMARY for case in self.cases)

    @property
    def partial_scored_count(self) -> int:
        return sum(case.role is BenchmarkCaseRole.PARTIAL for case in self.cases)


def load_benchmark_suite(path: str | Path) -> BenchmarkSuite:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("benchmark suite root must be a JSON object")
    return BenchmarkSuite.from_dict(payload)


def validate_suite_references(
    suite: BenchmarkSuite,
    *,
    repo_root: str | Path,
) -> None:
    """Validate manifest references without exposing labels to runtime code."""
    root = Path(repo_root)
    for case in suite.cases:
        benchmark_path = root / case.benchmark_path
        if not benchmark_path.is_file():
            raise ValueError(f"missing benchmark file: {case.benchmark_path}")
        payload = json.loads(benchmark_path.read_text(encoding="utf-8"))
        if payload.get("benchmark_id") != case.benchmark_id:
            raise ValueError(
                f"benchmark ID mismatch for {case.benchmark_path}: "
                f"expected {case.benchmark_id!r}, got {payload.get('benchmark_id')!r}"
            )
        if payload.get("knowledge_policy") != GROUND_TRUTH_POLICY:
            raise ValueError(
                f"unsafe benchmark knowledge policy: {case.benchmark_path}"
            )
