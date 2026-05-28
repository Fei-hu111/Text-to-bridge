"""Geometry planning agent."""

from __future__ import annotations

from bridge_fem_agent.agents.base import ModelProductionState


class GeometryAgent:
    """Derive station coordinates and Abaqus wire topology from bridge semantics."""

    def plan(self, state: ModelProductionState) -> ModelProductionState:
        model = state.semantic
        stations = model.stations_m
        support_stations = sorted({round(support.x_m, 9) for support in model.supports})
        breakpoints = sorted(set(stations + support_stations))
        state.model_plan["geometry"] = {
            "coordinate_system": "X longitudinal, Y transverse, Z vertical",
            "total_length_m": model.total_length_m,
            "span_stations_m": stations,
            "wire_breakpoints_m": breakpoints,
            "girder_axis": [(x_m, 0.0, 0.0) for x_m in breakpoints],
        }
        state.note("GeometryAgent", f"Planned {len(breakpoints) - 1} wire segments over {model.total_length_m:.3f} m.")
        return state

