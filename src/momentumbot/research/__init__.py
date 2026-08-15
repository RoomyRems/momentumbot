"""Research utilities for corpus analysis and evidence-backed strategy rules."""

from .corpus import CorpusAudit, CorpusRecord, audit_corpus, load_jsonl, split_as_of
from .evidence import DecisionRole, EvidenceMode, ObservationType, StrategyRule

__all__ = [
    "CorpusAudit",
    "CorpusRecord",
    "DecisionRole",
    "EvidenceMode",
    "ObservationType",
    "StrategyRule",
    "audit_corpus",
    "load_jsonl",
    "split_as_of",
]
