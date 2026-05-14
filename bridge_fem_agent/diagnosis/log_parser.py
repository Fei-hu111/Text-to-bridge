"""Parse Abaqus text outputs for warnings and errors."""

from __future__ import annotations

import re
from dataclasses import dataclass

from bridge_fem_agent.runner.job_monitor import JobArtifacts


@dataclass(frozen=True)
class LogFinding:
    severity: str
    source: str
    message: str


class LogParser:
    """Extract diagnostic lines from ``.log``, ``.msg``, ``.dat``, and ``.sta``."""

    LINE_RE = re.compile(
        r"(\*\*\*ERROR|ABAQUS ERROR|WARNING|ZERO PIVOT|TOO MANY ATTEMPTS|DIVERGENCE|"
        r"TERMINATED|FAILED|WMI|LICENSE.*(ERROR|FAILED|DENIED)|CPUS?.*(EXCEEDS|ERROR))",
        re.IGNORECASE,
    )

    def parse(self, artifacts: JobArtifacts) -> list[LogFinding]:
        findings: list[LogFinding] = []
        for path in artifacts.text_files():
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                stripped = line.strip()
                upper = stripped.upper()
                if re.match(r"^0\s+.*(WARNING|WARNINGS|ERROR|ERRORS)\b", upper):
                    continue
                if "ERROR TOLERANCE" in upper:
                    continue
                if "DIVERGENCE" in upper and ("CHECK" in upper or "CUT-BACK FACTOR" in upper):
                    continue
                if self.LINE_RE.search(stripped):
                    severity = "error" if re.search(r"ERROR|TERMINATED|ZERO PIVOT", line, re.IGNORECASE) else "warning"
                    findings.append(LogFinding(severity=severity, source=path.name, message=stripped))
        return findings
