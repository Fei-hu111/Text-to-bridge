"""Isolated Abaqus subprocess wrapper."""

from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class AbaqusRunResult:
    job_name: str
    input_file: Path
    workdir: Path
    return_code: int
    command: list[str]
    dry_run: bool

    @property
    def succeeded(self) -> bool:
        return self.return_code == 0


class AbaqusRunner:
    """Run Abaqus jobs or synthesize outputs for workflow testing."""

    def __init__(self, abaqus_command: str = "abaqus", dry_run: bool = False) -> None:
        self.abaqus_command = abaqus_command
        self.dry_run = dry_run

    def run(self, input_file: Path, job_name: str, workdir: Path) -> AbaqusRunResult:
        LOGGER.info("Starting Abaqus job '%s' with input '%s'.", job_name, input_file)
        if self.dry_run:
            return self._dry_run(input_file, job_name, workdir)

        command = self._build_command(job_name, input_file)
        completed = self._run_subprocess(command, workdir)
        (workdir / f"{job_name}.stdout.txt").write_text(completed.stdout, encoding="utf-8")
        (workdir / f"{job_name}.stderr.txt").write_text(completed.stderr, encoding="utf-8")
        LOGGER.info("Abaqus job '%s' finished with return code %s.", job_name, completed.returncode)
        return AbaqusRunResult(job_name, input_file, workdir, completed.returncode, command, dry_run=False)

    def _build_command(self, job_name: str, input_file: Path) -> list[str]:
        split_args = shlex.split(self.abaqus_command, posix=(os.name != "nt"))
        if not split_args:
            split_args = ["abaqus"]
        executable = split_args[0].strip('"')
        resolved = shutil.which(executable) or executable
        return [resolved, *split_args[1:], f"job={job_name}", f"input={input_file.name}", "interactive"]

    def _run_subprocess(self, command: list[str], workdir: Path) -> subprocess.CompletedProcess[str]:
        suffix = Path(command[0]).suffix.lower()
        if os.name == "nt" and suffix in {".bat", ".cmd"}:
            # Windows batch launchers need shell mediation; Abaqus commonly
            # exposes ``abaqus.bat`` under SIMULIA\Commands.
            return subprocess.run(
                subprocess.list2cmdline(command),
                cwd=workdir,
                capture_output=True,
                text=True,
                check=False,
                shell=True,
            )
        return subprocess.run(command, cwd=workdir, capture_output=True, text=True, check=False)

    def _dry_run(self, input_file: Path, job_name: str, workdir: Path) -> AbaqusRunResult:
        """Create deterministic output files so the workflow is testable anywhere."""

        text = input_file.read_text(encoding="utf-8")
        command = ["DRY_RUN", f"job={job_name}", f"input={input_file.name}", "interactive"]
        has_error = "*Material" not in text or "*Step" not in text
        if has_error:
            log = "Abaqus dry-run failed: input is missing a material or analysis step.\n"
            msg = "***ERROR: MATERIAL OR STEP DEFINITION IS MISSING\n"
            sta = "THE ANALYSIS HAS BEEN TERMINATED DUE TO ERRORS\n"
            dat = "Abaqus dry-run completed with errors.\n"
            return_code = 1
        else:
            log = "Abaqus dry-run completed successfully.\n"
            msg = "THE ANALYSIS HAS COMPLETED SUCCESSFULLY\n"
            sta = "THE ANALYSIS HAS COMPLETED SUCCESSFULLY\n"
            dat = (
                "BRIDGE_FEM_AGENT_RESULTS\n"
                "MAX_DISPLACEMENT_U 1.250000e-03\n"
                "MAX_STRESS_S 8.420000e+06\n"
                "SUPPORT_REACTION_LEFT 1.500000e+05\n"
                "SUPPORT_REACTION_RIGHT 1.500000e+05\n"
                "FREQUENCY_MODE_1 4.250000e+00\n"
            )
            return_code = 0

        (workdir / f"{job_name}.log").write_text(log, encoding="utf-8")
        (workdir / f"{job_name}.msg").write_text(msg, encoding="utf-8")
        (workdir / f"{job_name}.sta").write_text(sta, encoding="utf-8")
        (workdir / f"{job_name}.dat").write_text(dat, encoding="utf-8")
        LOGGER.info("Dry-run outputs written for job '%s'.", job_name)
        return AbaqusRunResult(job_name, input_file, workdir, return_code, command, dry_run=True)
