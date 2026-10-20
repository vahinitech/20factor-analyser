# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
#
# results.py - the FactorScore/SectionScore/AnalysisResult dataclasses
# the /report-python endpoint serializes (scoring.build_analysis).

from dataclasses import dataclass, field


@dataclass
class FactorScore:
    n: int
    sec: str
    name: str
    ex: str
    target: str
    tip: str
    score: float
    score100: int
    band: str
    value: str
    evidence: str
    based_on: str = None
    conf: str = "measured"
    imu_measured: bool = False
    unmeasured: bool = False
    unmeasured_reason: str = None
    unmeasured_kind: str = None
    scoring_inputs: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "n": self.n,
            "sec": self.sec,
            "name": self.name,
            "ex": self.ex,
            "target": self.target,
            "conf": self.conf,
            "tip": self.tip,
            "score": self.score,
            "score100": self.score100,
            "band": self.band,
            "value": self.value,
            "evidence": self.evidence,
            "imuMeasured": self.imu_measured,
            "unmeasured": self.unmeasured,
            "unmeasuredReason": self.unmeasured_reason,
            "unmeasuredKind": self.unmeasured_kind,
            "basedOn": self.based_on,
            "scoringInputs": self.scoring_inputs,
        }


@dataclass
class SectionScore:
    id: str
    name: str
    weight: float
    blurb: str
    factors: list = field(default_factory=list)
    avg: float = None
    avg100: int = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "weight": self.weight,
            "blurb": self.blurb,
            "avg": self.avg,
            "avg100": self.avg100,
            "factors": [f.to_dict() for f in self.factors],
            "scoredCount": sum(not f.unmeasured for f in self.factors),
        }


@dataclass
class AnalysisResult:
    results: list
    sections: list
    overall: int
    overall_measured: int
    measured_count: int
    top_weak: list
    top_strong: list
    source: str = "python"
    plain_groups: list = None
    coach_view: dict = None
    baseline_drift: dict = None
    zone_profile: dict = None
    tbar_profile: dict = None
    style_profile: dict = None
    coach_tips: list = None
    tip_pillars: dict = None

    def to_dict(self) -> dict:
        return {
            "results": [r.to_dict() for r in self.results],
            "sections": [s.to_dict() for s in self.sections],
            "overall": self.overall,
            "overallMeasured": self.overall_measured,
            "measuredCount": self.measured_count,
            "topWeak": [r.to_dict() for r in self.top_weak],
            "topStrong": [r.to_dict() for r in self.top_strong],
            "source": self.source,
            "plainGroups": self.plain_groups,
            "coachView": self.coach_view,
            "baselineDrift": self.baseline_drift,
            "zoneProfile": self.zone_profile,
            "tbarProfile": self.tbar_profile,
            "styleProfile": self.style_profile,
            "coachTips": self.coach_tips,
            "tipPillars": self.tip_pillars,
        }
