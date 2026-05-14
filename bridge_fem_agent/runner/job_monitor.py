"""Collect and summarize Abaqus job artifacts."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from bridge_fem_agent.config import ABAQUS_OUTPUT_EXTENSIONS


@dataclass(frozen=True)
class JobArtifacts:
    job_name: str
    workdir: Path
    files: dict[str, Path] = field(default_factory=dict)

    def text_files(self) -> list[Path]:
        return [path for ext, path in self.files.items() if ext in {".log", ".msg", ".dat", ".sta"} and path.exists()]


class JobMonitor:
    """Locate Abaqus output files and infer coarse job status."""

    def collect(self, job_name: str, workdir: Path) -> JobArtifacts:
        files = {ext: workdir / f"{job_name}{ext}" for ext in ABAQUS_OUTPUT_EXTENSIONS}
        files[".stdout.txt"] = workdir / f"{job_name}.stdout.txt"
        files[".stderr.txt"] = workdir / f"{job_name}.stderr.txt"
        return JobArtifacts(job_name=job_name, workdir=workdir, files=files)

    def status(self, artifacts: JobArtifacts) -> str:
        sta = artifacts.files.get(".sta")
        msg = artifacts.files.get(".msg")
        text = ""
        stdout = artifacts.files.get(".stdout.txt")
        stderr = artifacts.files.get(".stderr.txt")
        for path in (sta, msg, stdout, stderr):
            if path and path.exists():
                text += path.read_text(encoding="utf-8", errors="ignore").upper()
        if "COMPLETED SUCCESSFULLY" in text:
            return "success"
        if "ERROR" in text or "TERMINATED" in text or "ABORT" in text or "FAILED" in text:
            return "failed"
        return "unknown"
