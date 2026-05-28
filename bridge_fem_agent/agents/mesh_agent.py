"""Mesh planning agent."""

from __future__ import annotations

from bridge_fem_agent.agents.base import ModelProductionState


class MeshAgent:
    """Choose mesh size and mandatory mesh breakpoints."""

    def plan(self, state: ModelProductionState) -> ModelProductionState:
        model = state.semantic
        shortest_span = min(model.spans_m)
        target = model.mesh.target_size_m
        if target is None:
            target = max(shortest_span / max(model.mesh.elements_per_span, 1), shortest_span / 80.0)
        target = max(float(target), 0.05)
        state.model_plan["mesh"] = {
            "target_size_m": target,
            "element_type": model.mesh.element_type,
            "deviation_factor": 0.1,
            "min_size_factor": 0.1,
            "refine_at_supports": model.mesh.refine_at_supports,
            "mandatory_breakpoints_m": state.model_plan["geometry"]["wire_breakpoints_m"],
        }
        state.note("MeshAgent", f"Selected target mesh size {target:.3f} m with support breakpoints preserved.")
        return state

