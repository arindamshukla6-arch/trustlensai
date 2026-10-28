"""Core data structures shared by analysis modules, scoring and reports."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class SignalResult(str, Enum):
    NO_CONCERN = "no_concern"      # check ran, nothing notable found
    CONCERN = "concern"            # check ran, found an indicator worth human attention
    INCONCLUSIVE = "inconclusive"  # check ran but input quality/evidence was insufficient
    NOT_RUN = "not_run"            # input missing or capability unavailable
    ERROR = "error"                # check crashed or input unreadable

    @property
    def completed(self) -> bool:
        return self in (SignalResult.NO_CONCERN, SignalResult.CONCERN)


class Quality(str, Enum):
    GOOD = "good"
    ADEQUATE = "adequate"
    POOR = "poor"
    UNKNOWN = "unknown"


class RiskBand(str, Enum):
    LOW = "Low"
    MODERATE = "Moderate"
    ELEVATED = "Elevated"
    INCONCLUSIVE = "Inconclusive"


class CaseStatus(str, Enum):
    """Case workflow status.

    Note there is deliberately NO automatic 'rejected' status. Automated
    analysis can only move a case to AWAITING_REVIEW. Every other value is set
    exclusively by reviewer.record_decision() with a named human reviewer.
    """
    DRAFT = "draft"
    AWAITING_REVIEW = "awaiting_review"
    VERIFIED = "verified"
    FURTHER_REVIEW = "requires_further_review"
    CONFIRMED_CONCERN = "confirmed_concern_after_investigation"


HUMAN_DECISIONS = (CaseStatus.VERIFIED, CaseStatus.FURTHER_REVIEW, CaseStatus.CONFIRMED_CONCERN)

DECISION_LABELS = {
    CaseStatus.VERIFIED: "Verified",
    CaseStatus.FURTHER_REVIEW: "Requires further review",
    CaseStatus.CONFIRMED_CONCERN: "Confirmed concern after investigation",
}

STATUS_LABELS = {
    CaseStatus.DRAFT: "Draft",
    CaseStatus.AWAITING_REVIEW: "Awaiting human review",
    **DECISION_LABELS,
}


@dataclass
class Finding:
    """One concrete observation inside a signal (e.g. a document check)."""
    check: str
    observation: str
    severity: str = "info"          # info | low | medium | high
    means: str = ""                 # what this can indicate
    does_not_mean: str = ""         # what this cannot establish
    location: str = ""              # page, timestamp, region...

    SEVERITY_VALUE = {"info": 0.0, "low": 0.3, "medium": 0.6, "high": 1.0}

    @property
    def value(self) -> float:
        return self.SEVERITY_VALUE.get(self.severity, 0.0)


@dataclass
class Signal:
    key: str
    name: str
    result: SignalResult
    evidence: list[str] = field(default_factory=list)
    quality: Quality = Quality.UNKNOWN
    method: str = ""
    limitations: list[str] = field(default_factory=list)
    confidence: Optional[float] = None       # only set when genuinely calculated
    confidence_basis: str = "Not calculated: rule-based heuristic without calibrated confidence."
    severity: float = 0.0                    # 0..1, how strong the indicator is (CONCERN only)
    findings: list[Finding] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)   # name -> stored file path
    recapture_recommended: bool = False
    error: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["result"] = self.result.value
        d["quality"] = self.quality.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Signal":
        d = dict(d)
        d["result"] = SignalResult(d["result"])
        d["quality"] = Quality(d.get("quality", "unknown"))
        d["findings"] = [Finding(**f) for f in d.get("findings", [])]
        return cls(**d)

    @classmethod
    def not_run(cls, key: str, name: str, reason: str, method: str = "") -> "Signal":
        return cls(key=key, name=name, result=SignalResult.NOT_RUN,
                   evidence=[reason], method=method)

    @classmethod
    def failed(cls, key: str, name: str, error: str, method: str = "") -> "Signal":
        return cls(key=key, name=name, result=SignalResult.ERROR,
                   evidence=["The check could not be completed."], error=error, method=method)


@dataclass
class RiskAssessment:
    """Output of scoring. Advisory only: it has no power to change case status."""
    band: RiskBand
    score: float
    reasons: list[str]
    contributions: dict[str, float]
    completed_signals: list[str]
    incomplete_signals: list[str]
    recapture_recommended: bool
    next_steps: list[str]
    disclaimer: str

    def to_dict(self) -> dict:
        d = asdict(self)
        d["band"] = self.band.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "RiskAssessment":
        d = dict(d)
        d["band"] = RiskBand(d["band"])
        return cls(**d)
