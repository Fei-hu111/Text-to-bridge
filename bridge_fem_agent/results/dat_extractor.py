"""Extract lightweight results from Abaqus ``.dat`` output."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class AnalysisResults:
    max_displacement: float | None = None
    max_stress: float | None = None
    support_reactions: dict[str, float] = field(default_factory=dict)
    modal_frequencies: list[float] = field(default_factory=list)


class DatExtractor:
    """Read deterministic result markers and common numeric patterns from ``.dat``."""

    PATTERNS = {
        "max_displacement": re.compile(r"MAX_DISPLACEMENT_U\s+([-+0-9.eE]+)"),
        "max_stress": re.compile(r"MAX_STRESS_S\s+([-+0-9.eE]+)"),
        "reaction_left": re.compile(r"SUPPORT_REACTION_LEFT\s+([-+0-9.eE]+)"),
        "reaction_right": re.compile(r"SUPPORT_REACTION_RIGHT\s+([-+0-9.eE]+)"),
        "frequency": re.compile(r"FREQUENCY_MODE_\d+\s+([-+0-9.eE]+)"),
    }

    def extract(self, dat_path: Path) -> AnalysisResults:
        if not dat_path.exists():
            return AnalysisResults()
        text = dat_path.read_text(encoding="utf-8", errors="ignore")
        left = self._first_float("reaction_left", text)
        right = self._first_float("reaction_right", text)
        reactions = {}
        if left is not None:
            reactions["left"] = left
        if right is not None:
            reactions["right"] = right
        frequencies = [float(value) for value in self.PATTERNS["frequency"].findall(text)]
        return AnalysisResults(
            max_displacement=self._first_float("max_displacement", text),
            max_stress=self._first_float("max_stress", text),
            support_reactions=reactions,
            modal_frequencies=frequencies,
        )

    def _first_float(self, name: str, text: str) -> float | None:
        match = self.PATTERNS[name].search(text)
        return float(match.group(1)) if match else None
