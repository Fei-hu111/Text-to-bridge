"""Generate Abaqus ``.inp`` files from bridge task data.

The first implementation creates a representative 3D beam model using B31
elements. It is deliberately simple: the intent is to validate the workflow,
not to replace project-specific bridge modelling decisions.
"""

from __future__ import annotations

import logging
from pathlib import Path

from bridge_fem_agent.schemas.bridge_schema import BridgeTask

LOGGER = logging.getLogger(__name__)


class InpBuilder:
    """Build deterministic Abaqus input files for supported bridge schemas."""

    def __init__(self, node_count: int = 11) -> None:
        if node_count < 2:
            raise ValueError("node_count must be at least 2.")
        self.node_count = node_count

    def write_initial_inp(self, task: BridgeTask, workdir: Path) -> Path:
        """Write ``jobname_attempt_0.inp`` without touching any source file."""

        path = workdir / f"{task.project_name}_attempt_0.inp"
        path.write_text(self.build(task), encoding="utf-8")
        LOGGER.info("Generated initial Abaqus input file: %s", path)
        return path

    def build(self, task: BridgeTask) -> str:
        span = task.geometry.span_m
        spacing = span / (self.node_count - 1)
        nodes = [(idx + 1, idx * spacing, 0.0, 0.0) for idx in range(self.node_count)]
        elements = [(idx + 1, idx + 1, idx + 2) for idx in range(self.node_count - 1)]

        tributary_width = task.geometry.deck_width_m
        nominal_depth = max(0.8, span / 30.0)
        uniform_line_load = task.loads.uniform_deck_load_pa * tributary_width

        lines: list[str] = [
            "*Heading",
            f"** Bridge FEM Agent generated model: {task.project_name}",
            "** TODO: add future LLM reasoning hook for model idealization choices.",
            "*Preprint, echo=NO, model=NO, history=NO, contact=NO",
            "*Material, name=CONCRETE",
            "*Density",
            f"{task.concrete.density_kg_m3:.6g}",
            "*Elastic",
            f"{task.concrete.elastic_modulus_pa:.6g}, {task.concrete.poisson_ratio:.6g}",
            "*Part, name=BRIDGE_GIRDER",
            "*Node",
        ]

        lines.extend(f"{node_id}, {x:.6f}, {y:.6f}, {z:.6f}" for node_id, x, y, z in nodes)
        lines.append("*Element, type=B31, elset=EALL")
        lines.extend(f"{elem_id}, {n1}, {n2}" for elem_id, n1, n2 in elements)
        lines.extend(
            [
                "*Nset, nset=LEFT_SUPPORT",
                "1",
                "*Nset, nset=RIGHT_SUPPORT",
                str(self.node_count),
                "*Nset, nset=ALL_NODES, generate",
                f"1, {self.node_count}, 1",
                "*Elset, elset=EALL, generate",
                f"1, {self.node_count - 1}, 1",
                "*Beam Section, elset=EALL, material=CONCRETE, section=RECT",
                f"{tributary_width:.6f}, {nominal_depth:.6f}",
                "0., 0., -1.",
                "*End Part",
                "*Assembly, name=ASSEMBLY",
                "*Instance, name=BRIDGE_GIRDER-1, part=BRIDGE_GIRDER",
                "*End Instance",
                "*Nset, nset=LEFT_SUPPORT, instance=BRIDGE_GIRDER-1",
                "1",
                "*Nset, nset=RIGHT_SUPPORT, instance=BRIDGE_GIRDER-1",
                str(self.node_count),
                "*Elset, elset=EALL, instance=BRIDGE_GIRDER-1, generate",
                f"1, {self.node_count - 1}, 1",
                "*End Assembly",
                "** Boundary conditions",
            ]
        )
        lines.extend(self._boundary_lines(task))

        if task.analysis_type == "frequency":
            lines.extend(["*Step, name=FREQUENCY_STEP", "*Frequency", "5"])
        else:
            lines.extend(["*Step, name=STATIC_STEP, nlgeom=NO", "*Static", "1., 1., 1e-05, 1."])

        lines.extend(["** Loads"])
        if task.loads.gravity:
            lines.extend(["*Dload", "EALL, GRAV, 9.81, 0., 0., -1."])
        if uniform_line_load:
            lines.extend(["*Dload", f"EALL, PY, {-uniform_line_load:.6f}"])

        lines.extend(
            [
                "*Output, field",
                "*Node Output",
                "U, RF",
                "*Element Output, directions=YES",
                "S",
                "*Output, history",
                "*Node Output, nset=LEFT_SUPPORT",
                "RF",
                "*End Step",
                "",
            ]
        )
        return "\n".join(lines)

    def _boundary_lines(self, task: BridgeTask) -> list[str]:
        lines: list[str] = []
        left = task.boundary_conditions.left_support
        right = task.boundary_conditions.right_support

        if left == "fixed":
            lines.extend(["*Boundary", "LEFT_SUPPORT, 1, 6, 0."])
        else:
            lines.extend(["*Boundary", "LEFT_SUPPORT, 1, 3, 0."])
            lines.extend(["*Boundary", "LEFT_SUPPORT, 4, 4, 0."])

        if right == "fixed":
            lines.extend(["*Boundary", "RIGHT_SUPPORT, 1, 6, 0."])
        elif right == "roller":
            lines.extend(["*Boundary", "RIGHT_SUPPORT, 2, 3, 0."])
        else:
            lines.extend(["*Boundary", "RIGHT_SUPPORT, 1, 3, 0."])
        return lines
