"""Repair orchestration that writes new attempt files only."""

from __future__ import annotations

import logging
from pathlib import Path

from bridge_fem_agent.diagnosis.error_classifier import DiagnosticIssue
from bridge_fem_agent.inp.inp_parser import InpParser
from bridge_fem_agent.repair.repair_rules import RepairAction, RepairRules

LOGGER = logging.getLogger(__name__)


class RepairEngine:
    """Create repaired ``.inp`` attempts without overwriting prior files."""

    def __init__(self) -> None:
        self.parser = InpParser()
        self.rules = RepairRules()

    def repair(self, current_inp: Path, issues: list[DiagnosticIssue], job_name: str, attempt: int, workdir: Path) -> tuple[Path | None, list[RepairAction]]:
        summary = self.parser.parse(current_inp)
        repaired_text, actions = self.rules.apply(summary, issues)
        if not actions:
            LOGGER.info("No deterministic repair was applicable for %s.", current_inp)
            return None, []

        next_path = workdir / f"{job_name}_attempt_{attempt}.inp"
        if next_path.exists():
            raise FileExistsError(f"refusing to overwrite existing repair attempt: {next_path}")
        next_path.write_text(repaired_text, encoding="utf-8")
        LOGGER.info("Wrote repaired input file: %s", next_path)
        return next_path, actions
