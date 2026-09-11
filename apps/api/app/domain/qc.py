"""Structured QC report (spec §16 P7): severity levels and a deterministic pass/fail rule."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    BLOCKER = "blocker"


FAILING = frozenset({Severity.ERROR, Severity.BLOCKER})


class QCFinding(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: str = Field(max_length=80)
    severity: Severity = Severity.WARNING
    message: str = Field(max_length=2000)
    artifact_id: str | None = None
    location: str | None = Field(default=None, max_length=200)


class QCReport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    passed: bool
    findings: list[QCFinding] = Field(default_factory=list)
    checks_run: list[str] = Field(default_factory=list)
    summary: str = ""
    artifact_ids: list[str] = Field(default_factory=list)

    @property
    def failing(self) -> list[QCFinding]:
        return [f for f in self.findings if f.severity in FAILING]


def build_report(
    findings: list[QCFinding], *, checks_run: list[str], artifact_ids: list[str] | None = None
) -> QCReport:
    failing = [f for f in findings if f.severity in FAILING]
    passed = not failing
    summary = "QC passed" if passed else f"QC failed: {len(failing)} blocking finding(s)"
    if findings and passed:
        summary += f" with {len(findings)} advisory note(s)"
    return QCReport(
        passed=passed,
        findings=findings,
        checks_run=checks_run,
        summary=summary,
        artifact_ids=artifact_ids or [],
    )


def parse_report(value: Any) -> QCReport | None:
    """Accepts a dict produced by an agent/tool; returns None when it is not a QC report."""
    if not isinstance(value, dict):
        return None
    candidate = value.get("qc_report", value)
    if not isinstance(candidate, dict) or "passed" not in candidate:
        return None
    try:
        return QCReport.model_validate(candidate)
    except Exception:
        return None
