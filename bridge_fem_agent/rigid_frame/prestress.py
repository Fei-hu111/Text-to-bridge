"""Shared prestress planning helpers for rigid-frame Abaqus builders.

The V6 workflow models bonded tendons as embedded T3D2 elements.  A uniform
temperature reduction produces a free contraction strain in the prestress
steel; the EmbeddedRegion constraint transfers the resulting tendon tension
and concrete compression into the bridge model.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from bridge_fem_agent.rigid_frame.design import RigidFrameDesign
from bridge_fem_agent.rigid_frame.schema import RigidFrameInput

LOGGER = logging.getLogger(__name__)

PRESTRESS_ALPHA_PER_C = 1.2e-5
REASONABLE_EFFECTIVE_STRESS_MIN_PA = 9.0e8
REASONABLE_EFFECTIVE_STRESS_MAX_PA = 1.4e9


def tendon_prestress_plan(group: Any, task: RigidFrameInput) -> dict[str, Any]:
    """Return serializable tendon data with the V6 thermal-strain parameters."""

    data = group.__dict__.copy()
    area_total_m2 = float(group.area_each_m2) * int(group.count)
    total_force_n = float(group.total_force_n)
    effective_force_n = total_force_n * task.prestress_effective_ratio
    effective_stress_pa = effective_force_n / max(area_total_m2, 1.0e-12)
    delta_temperature_c = -effective_stress_pa / (
        task.materials.prestress_elastic_modulus_pa * PRESTRESS_ALPHA_PER_C
    )
    data.update(
        {
            "area_total_m2": area_total_m2,
            "total_force_n": total_force_n,
            "effective_force_n": effective_force_n,
            "effective_stress_pa": effective_stress_pa,
            "delta_temperature_c": delta_temperature_c,
            "stress_reasonable": (
                REASONABLE_EFFECTIVE_STRESS_MIN_PA
                <= effective_stress_pa
                <= REASONABLE_EFFECTIVE_STRESS_MAX_PA
            ),
        }
    )
    return data


def prestress_plan(task: RigidFrameInput, design: RigidFrameDesign) -> dict[str, Any]:
    """Build an auditable prestress summary shared by scripts and reports."""

    tendons = [tendon_prestress_plan(group, task) for group in design.tendon_groups]
    return {
        "prestress_mode": task.prestress_mode,
        "prestress_alpha_per_c": PRESTRESS_ALPHA_PER_C,
        "prestress_effective_ratio": task.prestress_effective_ratio,
        "prestress_elastic_modulus_pa": task.materials.prestress_elastic_modulus_pa,
        "reasonable_effective_stress_range_pa": [
            REASONABLE_EFFECTIVE_STRESS_MIN_PA,
            REASONABLE_EFFECTIVE_STRESS_MAX_PA,
        ],
        "tendon_groups": tendons,
        "validation_notes": [
            "Prestress-only response should show an upward camber tendency at span regions.",
            "Tendon S11 should be close to the requested effective prestress after restraint effects.",
            "Concrete section stress should follow the expected -P/A +/- Pe/W tendency.",
            "Thermal-strain mode is a bonded-tendon approximation; friction, anchorage slip, creep, shrinkage, and staged losses remain future work.",
        ],
    }


def write_prestress_verification(task: RigidFrameInput, design: RigidFrameDesign, workdir: Path) -> Path:
    """Write and log the tendon-by-tendon V6 prestress verification plan."""

    path = workdir / "prestress_verification.json"
    summary = prestress_plan(task, design)
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    LOGGER.info(
        "Prestress mode=%s effective_ratio=%.3f alpha=%.3e /C",
        task.prestress_mode,
        task.prestress_effective_ratio,
        PRESTRESS_ALPHA_PER_C,
    )
    for tendon in summary["tendon_groups"]:
        LOGGER.info(
            "Tendon %s: Pe=%.6e N Ap=%.6e m2 sigma_pe=%.3f MPa delta_T=%.3f C reasonable=%s",
            tendon["name"],
            tendon["effective_force_n"],
            tendon["area_total_m2"],
            tendon["effective_stress_pa"] / 1.0e6,
            tendon["delta_temperature_c"],
            tendon["stress_reasonable"],
        )
    return path
