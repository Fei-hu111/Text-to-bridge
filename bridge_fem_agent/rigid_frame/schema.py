"""Semantic schema for V3 three-span continuous rigid-frame bridges."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


class RigidFrameSchemaError(ValueError):
    """Raised when V3 rigid-frame input data is incomplete."""


@dataclass(frozen=True)
class RigidFrameTargets:
    max_deflection_ratio: float = 600.0
    max_compressive_stress_pa: float = 1.8e7
    max_tensile_stress_pa: float = 1.8e6
    max_iterations: int = 8


@dataclass(frozen=True)
class RigidFrameMaterials:
    girder_concrete: str = "C50"
    pier_concrete: str = "C40"
    prestress_steel: str = "1860MPa"
    concrete_density_kg_m3: float = 2500.0
    girder_elastic_modulus_pa: float = 3.45e10
    pier_elastic_modulus_pa: float = 3.25e10
    concrete_poisson_ratio: float = 0.2
    prestress_elastic_modulus_pa: float = 1.95e11
    tendon_jacking_stress_pa: float = 1.395e9


@dataclass(frozen=True)
class RigidFrameInput:
    project_name: str
    spans_m: list[float]
    deck_width_m: float = 12.5
    pier_height_m: float | None = None
    roadway_load_pa: float = 5000.0
    human_load_pa: float = 2500.0
    second_dead_load_pa: float = 2500.0
    materials: RigidFrameMaterials = field(default_factory=RigidFrameMaterials)
    targets: RigidFrameTargets = field(default_factory=RigidFrameTargets)

    @property
    def side_span_left_m(self) -> float:
        return self.spans_m[0]

    @property
    def main_span_m(self) -> float:
        return self.spans_m[1]

    @property
    def side_span_right_m(self) -> float:
        return self.spans_m[2]

    @property
    def total_length_m(self) -> float:
        return sum(self.spans_m)

    @property
    def pier_stations_m(self) -> tuple[float, float]:
        return (self.side_span_left_m, self.side_span_left_m + self.main_span_m)

    @property
    def resolved_pier_height_m(self) -> float:
        return self.pier_height_m if self.pier_height_m is not None else max(20.0, 0.35 * self.main_span_m)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, path: Path) -> "RigidFrameInput":
        with path.open("r", encoding="utf-8") as handle:
            return cls.from_dict(json.load(handle))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RigidFrameInput":
        project_name = str(data.get("project_name", "rigid_frame_bridge")).strip()
        spans = data.get("spans_m")
        if spans is None or len(spans) != 3:
            raise RigidFrameSchemaError("V3 rigid-frame workflow requires exactly three spans in spans_m.")
        spans_m = [float(item) for item in spans]
        if any(span <= 0 for span in spans_m):
            raise RigidFrameSchemaError("All spans must be positive.")
        materials = _materials_from_dict(data.get("materials", {}))
        targets = _targets_from_dict(data.get("targets", {}), data.get("max_design_iterations"))
        return cls(
            project_name=project_name,
            spans_m=spans_m,
            deck_width_m=float(data.get("deck_width_m", data.get("deck", {}).get("width_m", 12.5))),
            pier_height_m=_optional_float(data.get("pier_height_m")),
            roadway_load_pa=float(data.get("roadway_load_pa", 5000.0)),
            human_load_pa=float(data.get("human_load_pa", 2500.0)),
            second_dead_load_pa=float(data.get("second_dead_load_pa", 2500.0)),
            materials=materials,
            targets=targets,
        )


def _materials_from_dict(data: dict[str, Any]) -> RigidFrameMaterials:
    defaults = RigidFrameMaterials()
    return RigidFrameMaterials(
        girder_concrete=str(data.get("girder_concrete", defaults.girder_concrete)),
        pier_concrete=str(data.get("pier_concrete", defaults.pier_concrete)),
        prestress_steel=str(data.get("prestress_steel", defaults.prestress_steel)),
        concrete_density_kg_m3=float(data.get("concrete_density_kg_m3", defaults.concrete_density_kg_m3)),
        girder_elastic_modulus_pa=float(data.get("girder_elastic_modulus_pa", defaults.girder_elastic_modulus_pa)),
        pier_elastic_modulus_pa=float(data.get("pier_elastic_modulus_pa", defaults.pier_elastic_modulus_pa)),
        concrete_poisson_ratio=float(data.get("concrete_poisson_ratio", defaults.concrete_poisson_ratio)),
        prestress_elastic_modulus_pa=float(data.get("prestress_elastic_modulus_pa", defaults.prestress_elastic_modulus_pa)),
        tendon_jacking_stress_pa=float(data.get("tendon_jacking_stress_pa", defaults.tendon_jacking_stress_pa)),
    )


def _targets_from_dict(data: dict[str, Any], max_iterations: Any = None) -> RigidFrameTargets:
    defaults = RigidFrameTargets()
    return RigidFrameTargets(
        max_deflection_ratio=float(data.get("max_deflection_ratio", defaults.max_deflection_ratio)),
        max_compressive_stress_pa=float(data.get("max_compressive_stress_pa", defaults.max_compressive_stress_pa)),
        max_tensile_stress_pa=float(data.get("max_tensile_stress_pa", defaults.max_tensile_stress_pa)),
        max_iterations=int(max_iterations if max_iterations is not None else data.get("max_iterations", defaults.max_iterations)),
    )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)

