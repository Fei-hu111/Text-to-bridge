"""Structured bridge semantics shared by V2 model-production agents.

The semantic model is the audit boundary between drawing/text understanding
and Abaqus model generation. Drawing agents may be fuzzy in the future, but
everything below this layer is deterministic and reviewable.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


class SemanticModelError(ValueError):
    """Raised when the bridge semantic model is incomplete or inconsistent."""


@dataclass(frozen=True)
class MaterialSpec:
    name: str
    elastic_modulus_pa: float
    poisson_ratio: float
    density_kg_m3: float


@dataclass(frozen=True)
class SectionSpec:
    name: str = "MainGirderSection"
    section_type: str = "rectangular"
    width_m: float = 10.0
    height_m: float = 1.0
    area_m2: float | None = None
    i11_m4: float | None = None
    i22_m4: float | None = None
    j_m4: float | None = None


@dataclass(frozen=True)
class SupportSpec:
    name: str
    x_m: float
    support_type: str


@dataclass(frozen=True)
class LoadSpec:
    load_type: str
    name: str
    value: float | None = None
    target: str = "main_girder"
    direction: str = "z"


@dataclass(frozen=True)
class MeshSpec:
    target_size_m: float | None = None
    elements_per_span: int = 30
    refine_at_supports: bool = True
    element_type: str = "B31"


@dataclass(frozen=True)
class BridgeSemanticModel:
    project_name: str
    bridge_type: str
    analysis_type: str
    spans_m: list[float]
    deck_width_m: float
    girder_count: int
    materials: dict[str, MaterialSpec]
    section: SectionSpec
    supports: list[SupportSpec]
    loads: list[LoadSpec]
    mesh: MeshSpec = field(default_factory=MeshSpec)
    model_level: str = "auto"
    source_notes: list[str] = field(default_factory=list)

    @property
    def total_length_m(self) -> float:
        return sum(self.spans_m)

    @property
    def stations_m(self) -> list[float]:
        stations = [0.0]
        running = 0.0
        for span in self.spans_m:
            running += span
            stations.append(round(running, 9))
        return stations

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, path: Path) -> "BridgeSemanticModel":
        with path.open("r", encoding="utf-8") as handle:
            return cls.from_dict(json.load(handle))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BridgeSemanticModel":
        project_name = str(_require(data, "project_name")).strip()
        if not project_name:
            raise SemanticModelError("project_name cannot be empty.")

        bridge_type = str(data.get("bridge_type", "continuous_girder")).strip()
        analysis_type = str(data.get("analysis_type", "static")).strip().lower()
        if analysis_type not in {"static", "frequency"}:
            raise SemanticModelError("analysis_type must be 'static' or 'frequency'.")

        spans = data.get("spans_m")
        if spans is None:
            geometry = _require(data, "geometry")
            spans = [float(_require(geometry, "span_m"))]
        spans_m = [float(item) for item in spans]
        if not spans_m or any(span <= 0.0 for span in spans_m):
            raise SemanticModelError("spans_m must contain positive span lengths.")

        deck_data = data.get("deck", {})
        geometry = data.get("geometry", {})
        deck_width_m = float(deck_data.get("width_m", geometry.get("deck_width_m", 10.0)))
        if deck_width_m <= 0.0:
            raise SemanticModelError("deck width must be positive.")
        girder_count = int(data.get("girder", {}).get("count", geometry.get("girder_count", 1)))
        if girder_count <= 0:
            raise SemanticModelError("girder_count must be positive.")

        materials = _parse_materials(data.get("materials", {}))
        section = _parse_section(data, deck_width_m)
        supports = _parse_supports(data, spans_m)
        loads = _parse_loads(data)
        mesh = _parse_mesh(data.get("mesh", {}))

        return cls(
            project_name=project_name,
            bridge_type=bridge_type,
            analysis_type=analysis_type,
            spans_m=spans_m,
            deck_width_m=deck_width_m,
            girder_count=girder_count,
            materials=materials,
            section=section,
            supports=supports,
            loads=loads,
            mesh=mesh,
            model_level=str(data.get("model_level", "auto")).lower(),
            source_notes=[str(item) for item in data.get("source_notes", [])],
        )


def _parse_materials(data: dict[str, Any]) -> dict[str, MaterialSpec]:
    if not data:
        data = {"concrete": {"elastic_modulus_pa": 3.45e10, "poisson_ratio": 0.2, "density_kg_m3": 2500}}
    parsed: dict[str, MaterialSpec] = {}
    for name, values in data.items():
        parsed[name.upper()] = MaterialSpec(
            name=name.upper(),
            elastic_modulus_pa=float(_require(values, "elastic_modulus_pa")),
            poisson_ratio=float(_require(values, "poisson_ratio")),
            density_kg_m3=float(_require(values, "density_kg_m3")),
        )
    return parsed


def _parse_section(data: dict[str, Any], deck_width_m: float) -> SectionSpec:
    girder = data.get("girder", {})
    section = data.get("section", {})
    section_type = str(section.get("type", girder.get("section_type", "rectangular"))).lower()
    height = float(section.get("height_m", girder.get("height_m", max(0.8, sum(data.get("spans_m", [30.0])) / 30.0))))
    width = float(section.get("width_m", girder.get("width_m", deck_width_m)))
    if height <= 0.0 or width <= 0.0:
        raise SemanticModelError("section width and height must be positive.")
    return SectionSpec(
        name=str(section.get("name", "MainGirderSection")),
        section_type=section_type,
        width_m=width,
        height_m=height,
        area_m2=_optional_float(section.get("area_m2")),
        i11_m4=_optional_float(section.get("i11_m4")),
        i22_m4=_optional_float(section.get("i22_m4")),
        j_m4=_optional_float(section.get("j_m4")),
    )


def _parse_supports(data: dict[str, Any], spans_m: list[float]) -> list[SupportSpec]:
    supports = data.get("supports")
    stations = [0.0]
    running = 0.0
    for span in spans_m:
        running += span
        stations.append(running)
    if supports is None:
        bc = data.get("boundary_conditions", {})
        supports = [
            {"name": "P0", "x_m": 0.0, "type": bc.get("left_support", "pinned")},
            {"name": f"P{len(stations) - 1}", "x_m": stations[-1], "type": bc.get("right_support", "roller")},
        ]
        for index, x_m in enumerate(stations[1:-1], start=1):
            supports.insert(index, {"name": f"P{index}", "x_m": x_m, "type": "roller"})
    parsed = [SupportSpec(str(item["name"]), float(item["x_m"]), str(item.get("type", item.get("support_type", "roller"))).lower()) for item in supports]
    return sorted(parsed, key=lambda item: item.x_m)


def _parse_loads(data: dict[str, Any]) -> list[LoadSpec]:
    raw_loads = data.get("loads", [])
    if isinstance(raw_loads, dict):
        loads = []
        if raw_loads.get("gravity", False):
            loads.append(LoadSpec(load_type="gravity", name="Gravity"))
        if "uniform_deck_load_pa" in raw_loads:
            loads.append(LoadSpec(load_type="uniform_deck_pressure", name="UniformDeckLoad", value=float(raw_loads["uniform_deck_load_pa"])))
        return loads
    return [
        LoadSpec(
            load_type=str(item.get("type", item.get("load_type", "gravity"))),
            name=str(item.get("name", item.get("type", "Load"))),
            value=_optional_float(item.get("value", item.get("value_pa"))),
            target=str(item.get("target", "main_girder")),
            direction=str(item.get("direction", "z")),
        )
        for item in raw_loads
    ]


def _parse_mesh(data: dict[str, Any]) -> MeshSpec:
    return MeshSpec(
        target_size_m=_optional_float(data.get("target_size_m")),
        elements_per_span=int(data.get("elements_per_span", 30)),
        refine_at_supports=bool(data.get("refine_at_supports", True)),
        element_type=str(data.get("element_type", "B31")),
    )


def _require(data: dict[str, Any], key: str) -> Any:
    if key not in data:
        raise SemanticModelError(f"missing required key: {key}")
    return data[key]


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)

