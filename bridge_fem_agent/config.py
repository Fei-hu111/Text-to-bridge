"""Runtime configuration for the bridge FEM workflow.

The defaults keep every generated artifact under the user supplied workdir.
Set ``ABAQUS_COMMAND`` if Abaqus is installed under a non-standard command name.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkflowConfig:
    """Configuration shared across runner, repair, and reporting modules."""

    abaqus_command: str = os.environ.get("ABAQUS_COMMAND", "abaqus")
    default_max_repairs: int = 3
    generated_node_count: int = 11
    dry_run: bool = False
    keep_intermediate_files: bool = True

    @staticmethod
    def ensure_workdir(workdir: Path) -> Path:
        """Create the run directory and return a resolved path."""

        workdir.mkdir(parents=True, exist_ok=True)
        return workdir.resolve()


ABAQUS_OUTPUT_EXTENSIONS = (".log", ".msg", ".dat", ".sta", ".odb")
