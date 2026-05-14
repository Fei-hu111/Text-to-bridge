"""ODB extraction via Abaqus Python when Abaqus is available."""

from __future__ import annotations

import json
import logging
import os
import shlex
import shutil
import subprocess
from pathlib import Path

LOGGER = logging.getLogger(__name__)


class OdbExtractor:
    """Extract high-fidelity results when Abaqus Python is available."""

    def __init__(self, abaqus_command: str = "abaqus") -> None:
        self.abaqus_command = abaqus_command

    def extract(self, odb_path: Path) -> dict[str, object]:
        if not odb_path.exists():
            return {"available": False, "reason": "ODB file not found."}
        script = Path(__file__).with_name("abaqus_odb_extract.py")
        output_path = odb_path.with_suffix(".odb_results.json")
        command = self._build_command(script, odb_path, output_path)
        completed = self._run_subprocess(command, odb_path.parent)
        odb_path.with_suffix(".odb_extract.stdout.txt").write_text(completed.stdout, encoding="utf-8")
        odb_path.with_suffix(".odb_extract.stderr.txt").write_text(completed.stderr, encoding="utf-8")

        if completed.returncode != 0 or not output_path.exists():
            LOGGER.warning("ODB extraction failed for %s.", odb_path)
            return {
                "available": True,
                "extracted": False,
                "reason": "Abaqus Python ODB extraction failed.",
                "return_code": completed.returncode,
            }
        return {"available": True, "extracted": True, "results": json.loads(output_path.read_text(encoding="utf-8"))}

    def _build_command(self, script: Path, odb_path: Path, output_path: Path) -> list[str]:
        split_args = shlex.split(self.abaqus_command, posix=(os.name != "nt"))
        if not split_args:
            split_args = ["abaqus"]
        executable = split_args[0].strip('"')
        resolved = shutil.which(executable) or executable
        return [resolved, *split_args[1:], "python", str(script), str(odb_path), str(output_path)]

    def _run_subprocess(self, command: list[str], workdir: Path) -> subprocess.CompletedProcess[str]:
        suffix = Path(command[0]).suffix.lower()
        if os.name == "nt" and suffix in {".bat", ".cmd"}:
            return subprocess.run(
                subprocess.list2cmdline(command),
                cwd=workdir,
                capture_output=True,
                text=True,
                check=False,
                shell=True,
            )
        return subprocess.run(command, cwd=workdir, capture_output=True, text=True, check=False)
