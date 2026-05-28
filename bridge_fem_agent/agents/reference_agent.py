"""Extract reusable modelling patterns from local Abaqus journal samples."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from bridge_fem_agent.agents.base import ModelProductionState


class ReferenceAgent:
    """Summarize local ``samples/**/*.jnl`` files without importing large CAE files."""

    KEYWORDS = {
        "wire_beam": re.compile(r"BaseWire|WirePolyLine|BeamSection|assignBeamSectionOrientation"),
        "solid_extrude": re.compile(r"BaseSolidExtrude|HomogeneousSolidSection"),
        "connector_support": re.compile(r"ConnectorSection|SectionAssignment\(region=Region"),
        "gravity": re.compile(r"Gravity\("),
        "pressure": re.compile(r"Pressure\("),
        "line_or_point_load": re.compile(r"LineLoad\(|ConcentratedForce\("),
        "mesh_seed": re.compile(r"seedPart|seedEdgeByNumber|generateMesh|setElementType"),
        "static_step": re.compile(r"StaticStep\("),
        "frequency_step": re.compile(r"FrequencyStep\("),
    }

    def analyze(self, state: ModelProductionState, samples_dir: Path | None) -> ModelProductionState:
        if samples_dir is None or not samples_dir.exists():
            state.note("ReferenceAgent", "No samples directory was provided; using built-in bridge modelling patterns.", "warning")
            state.reference_patterns = {"source_count": 0}
            return state

        patterns: dict[str, Any] = {"source_count": 0, "files": []}
        totals = {name: 0 for name in self.KEYWORDS}
        for path in samples_dir.rglob("*.jnl"):
            text = path.read_text(encoding="mbcs", errors="ignore")
            file_counts = {name: len(pattern.findall(text)) for name, pattern in self.KEYWORDS.items()}
            for name, count in file_counts.items():
                totals[name] += count
            patterns["files"].append({"path": str(path), "counts": file_counts})
            patterns["source_count"] += 1

        patterns["totals"] = totals
        patterns["dominant_style"] = "wire_beam" if totals["wire_beam"] >= totals["solid_extrude"] else "solid_extrude"
        state.reference_patterns = patterns
        state.note(
            "ReferenceAgent",
            f"Analyzed {patterns['source_count']} journal files; dominant sample style is {patterns['dominant_style']}.",
        )
        return state
