"""Safe editing helpers for Abaqus input files.

All methods return edited text. The workflow writes that text to a new
``*_attempt_N.inp`` file, never over the original or prior attempt.
"""

from __future__ import annotations

import re

from bridge_fem_agent.inp.inp_parser import InpSummary


class InpEditor:
    """Apply small, deterministic edits to Abaqus input text."""

    def ensure_default_material(self, summary: InpSummary, material_name: str = "CONCRETE") -> str:
        if material_name.upper() in summary.materials:
            return summary.text
        insertion = (
            f"*Material, name={material_name}\n"
            "*Density\n"
            "2500.\n"
            "*Elastic\n"
            "3.0e10, 0.2\n"
        )
        return self._insert_before_first(summary.text, "*Beam Section", insertion)

    def ensure_required_nset(self, summary: InpSummary, set_name: str) -> str:
        if set_name.upper() in summary.nsets:
            return summary.text
        if not summary.nodes:
            return summary.text

        node_id = min(summary.nodes) if "LEFT" in set_name.upper() else max(summary.nodes)
        block = f"*Nset, nset={set_name}\n{node_id}\n"
        return self._insert_before_first(summary.text, "*End Part", block)

    def ensure_step(self, summary: InpSummary) -> str:
        if summary.has_step:
            return summary.text
        block = (
            "*Step, name=STATIC_STEP, nlgeom=NO\n"
            "*Static\n"
            "1., 1., 1e-05, 1.\n"
            "*End Step\n"
        )
        return summary.text.rstrip() + "\n" + block

    def stabilize_zero_pivot(self, summary: InpSummary) -> str:
        """Add a minimal rotational restraint if no obvious stabilization exists."""

        pattern = re.compile(r"LEFT_SUPPORT\s*,\s*4\s*,\s*4", re.IGNORECASE)
        if pattern.search(summary.text):
            return summary.text
        return self._insert_after_first(summary.text, "*Boundary", "LEFT_SUPPORT, 4, 4, 0.\n")

    def add_static_controls(self, text: str) -> str:
        if "*Controls" in text:
            return text
        return self._insert_after_first(text, "*Static", "*Controls, parameters=field\n0.01, 1.0\n")

    def _insert_before_first(self, text: str, keyword: str, insertion: str) -> str:
        idx = text.lower().find(keyword.lower())
        if idx < 0:
            return text.rstrip() + "\n" + insertion
        return text[:idx] + insertion + text[idx:]

    def _insert_after_first(self, text: str, keyword: str, insertion: str) -> str:
        lines = text.splitlines(keepends=True)
        for index, line in enumerate(lines):
            if line.strip().lower().startswith(keyword.lower()):
                lines.insert(index + 1, insertion)
                return "".join(lines)
        return text.rstrip() + "\n" + insertion
