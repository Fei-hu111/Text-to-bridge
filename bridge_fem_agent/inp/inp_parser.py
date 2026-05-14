"""Small Abaqus input parser for deterministic repair rules.

This parser is intentionally conservative. It extracts the entities needed by
the repair engine without trying to become a complete Abaqus grammar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class InpSummary:
    path: Path
    text: str
    nodes: dict[int, tuple[float, float, float]] = field(default_factory=dict)
    elements: set[int] = field(default_factory=set)
    nsets: set[str] = field(default_factory=set)
    elsets: set[str] = field(default_factory=set)
    materials: set[str] = field(default_factory=set)
    referenced_materials: set[str] = field(default_factory=set)
    referenced_sets: set[str] = field(default_factory=set)
    has_step: bool = False


class InpParser:
    """Extract common Abaqus entities from an input file."""

    KEYWORD_RE = re.compile(r"^\s*\*(?P<keyword>[^,\s]+)(?P<args>.*)$")
    ARG_RE = re.compile(r"(?P<name>[A-Za-z_]+)\s*=\s*(?P<value>[^,]+)")

    def parse(self, path: Path) -> InpSummary:
        text = path.read_text(encoding="utf-8")
        nodes: dict[int, tuple[float, float, float]] = {}
        elements: set[int] = set()
        nsets: set[str] = set()
        elsets: set[str] = set()
        materials: set[str] = set()
        referenced_materials: set[str] = set()
        referenced_sets: set[str] = set()
        has_step = False

        active = ""
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("**"):
                continue
            match = self.KEYWORD_RE.match(line)
            if match:
                active = match.group("keyword").lower()
                args = self._parse_args(match.group("args"))
                if active == "nset" and "nset" in args:
                    nsets.add(args["nset"].upper())
                elif active == "elset" and "elset" in args:
                    elsets.add(args["elset"].upper())
                elif active == "element" and "elset" in args:
                    elsets.add(args["elset"].upper())
                elif active == "material" and "name" in args:
                    materials.add(args["name"].upper())
                elif active in {"solid section", "beam section", "shell section"}:
                    if "material" in args:
                        referenced_materials.add(args["material"].upper())
                    if "elset" in args:
                        referenced_sets.add(args["elset"].upper())
                elif active == "boundary":
                    pass
                elif active in {"dload", "cload"}:
                    pass
                elif active == "step":
                    has_step = True
                continue

            if active == "node":
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 4:
                    nodes[int(parts[0])] = (float(parts[1]), float(parts[2]), float(parts[3]))
            elif active == "element":
                parts = [p.strip() for p in line.split(",")]
                if parts and parts[0].isdigit():
                    elements.add(int(parts[0]))
            elif active in {"boundary", "dload", "cload"}:
                first = line.split(",", 1)[0].strip()
                if first:
                    referenced_sets.add(first.upper())

        return InpSummary(
            path=path,
            text=text,
            nodes=nodes,
            elements=elements,
            nsets=nsets,
            elsets=elsets,
            materials=materials,
            referenced_materials=referenced_materials,
            referenced_sets=referenced_sets,
            has_step=has_step,
        )

    def _parse_args(self, text: str) -> dict[str, str]:
        return {match.group("name").lower(): match.group("value").strip().upper() for match in self.ARG_RE.finditer(text)}
