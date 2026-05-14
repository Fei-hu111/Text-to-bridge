"""Classify Abaqus log findings into deterministic repair categories."""

from __future__ import annotations

import re
from dataclasses import dataclass

from bridge_fem_agent.diagnosis.log_parser import LogFinding


@dataclass(frozen=True)
class DiagnosticIssue:
    category: str
    severity: str
    message: str
    source: str


class ErrorClassifier:
    """Map raw Abaqus diagnostics to workflow categories."""

    PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
        ("environment_error", re.compile(r"(WMI|LICENSE|CPUS?|ABAQUS ERROR|COMMAND|PERMISSION)", re.IGNORECASE)),
        ("missing_set", re.compile(r"(NODE SET|ELEMENT SET|NSET|ELSET).*(NOT|HAS NOT|MISSING|UNKNOWN)", re.IGNORECASE)),
        ("undefined_material", re.compile(r"(MATERIAL).*(NOT|HAS NOT|MISSING|UNKNOWN|UNDEFINED)", re.IGNORECASE)),
        ("element_type_error", re.compile(r"(ELEMENT TYPE|UNKNOWN ELEMENT|INVALID ELEMENT)", re.IGNORECASE)),
        ("boundary_condition_error", re.compile(r"(BOUNDARY|BC).*(ERROR|INVALID|UNKNOWN)", re.IGNORECASE)),
        ("rigid_body_zero_pivot", re.compile(r"(ZERO PIVOT|RIGID BODY|SINGULAR MATRIX|NUMERICAL SINGULARITY)", re.IGNORECASE)),
        ("step_definition_error", re.compile(r"(STEP).*(ERROR|MISSING|INVALID|NOT DEFINED)", re.IGNORECASE)),
        ("load_definition_error", re.compile(r"(LOAD|DLOAD|CLOAD).*(ERROR|INVALID|UNKNOWN)", re.IGNORECASE)),
        ("non_convergence", re.compile(r"(TOO MANY ATTEMPTS|DIVERGENCE|DID NOT CONVERGE|CONVERGENCE)", re.IGNORECASE)),
    )

    def classify(self, findings: list[LogFinding]) -> list[DiagnosticIssue]:
        issues: list[DiagnosticIssue] = []
        for finding in findings:
            category = "unknown"
            for name, pattern in self.PATTERNS:
                if pattern.search(finding.message):
                    category = name
                    break
            issues.append(DiagnosticIssue(category, finding.severity, finding.message, finding.source))
        return issues
