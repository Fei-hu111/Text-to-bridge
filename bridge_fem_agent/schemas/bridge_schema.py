"""Dataclass schema and validation for bridge analysis task JSON.

The first version intentionally models only a simply supported girder bridge.
The schema is small, deterministic, and dependency-free so the workflow can be
tested on machines without additional Python packages.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class BridgeSchemaError(ValueError):
    """Raised when a bridge task JSON file is missing required data."""


@dataclass(frozen=True)
class Geometry:
    span_m: float
    deck_width_m: float
    girder_count: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Geometry":
        return cls(
            span_m=_positive_float(data, "span_m"),
            deck_width_m=_positive_float(data, "deck_width_m"),
            girder_count=_positive_int(data, "girder_count"),
        )


@dataclass(frozen=True)
class Material:
    elastic_modulus_pa: float
    poisson_ratio: float
    density_kg_m3: float

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Material":
        poisson = float(_require(data, "poisson_ratio"))
        if not 0.0 <= poisson < 0.5:
            raise BridgeSchemaError("materials.concrete.poisson_ratio must be in [0, 0.5).")
        return cls(
            elastic_modulus_pa=_positive_float(data, "elastic_modulus_pa"),
            poisson_ratio=poisson,
            density_kg_m3=_positive_float(data, "density_kg_m3"),
        )


@dataclass(frozen=True)
class Loads:
    gravity: bool
    uniform_deck_load_pa: float

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Loads":
        return cls(
            gravity=bool(data.get("gravity", False)),
            uniform_deck_load_pa=float(data.get("uniform_deck_load_pa", 0.0)),
        )


@dataclass(frozen=True)
class BoundaryConditions:
    left_support: str
    right_support: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BoundaryConditions":
        left = str(_require(data, "left_support")).lower()
        right = str(_require(data, "right_support")).lower()
        allowed = {"pinned", "roller", "fixed"}
        if left not in allowed or right not in allowed:
            raise BridgeSchemaError(f"support types must be one of {sorted(allowed)}.")
        return cls(left_support=left, right_support=right)


@dataclass(frozen=True)
class BridgeTask:
    project_name: str
    bridge_type: str
    analysis_type: str
    geometry: Geometry
    concrete: Material
    loads: Loads
    boundary_conditions: BoundaryConditions

    @classmethod
    def from_json(cls, path: Path) -> "BridgeTask":
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BridgeTask":
        project_name = str(_require(data, "project_name")).strip()
        bridge_type = str(_require(data, "bridge_type")).strip()
        analysis_type = str(_require(data, "analysis_type")).strip().lower()
        if not project_name:
            raise BridgeSchemaError("project_name cannot be empty.")
        if bridge_type != "simply_supported_girder":
            raise BridgeSchemaError("first version supports only bridge_type='simply_supported_girder'.")
        if analysis_type not in {"static", "frequency"}:
            raise BridgeSchemaError("analysis_type must be 'static' or 'frequency'.")

        materials = _require(data, "materials")
        if "concrete" not in materials:
            raise BridgeSchemaError("materials.concrete is required.")

        return cls(
            project_name=project_name,
            bridge_type=bridge_type,
            analysis_type=analysis_type,
            geometry=Geometry.from_dict(_require(data, "geometry")),
            concrete=Material.from_dict(materials["concrete"]),
            loads=Loads.from_dict(_require(data, "loads")),
            boundary_conditions=BoundaryConditions.from_dict(_require(data, "boundary_conditions")),
        )


def _require(data: dict[str, Any], key: str) -> Any:
    if key not in data:
        raise BridgeSchemaError(f"missing required key: {key}")
    return data[key]


def _positive_float(data: dict[str, Any], key: str) -> float:
    value = float(_require(data, key))
    if value <= 0.0:
        raise BridgeSchemaError(f"{key} must be positive.")
    return value


def _positive_int(data: dict[str, Any], key: str) -> int:
    value = int(_require(data, key))
    if value <= 0:
        raise BridgeSchemaError(f"{key} must be positive.")
    return value
