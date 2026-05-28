"""Boundary and support planning agent."""

from __future__ import annotations

from bridge_fem_agent.agents.base import ModelProductionState


class BoundaryAgent:
    """Translate engineering support semantics into Abaqus beam DOF constraints."""

    DOF_MAP = {
        "fixed": {"u1": 0.0, "u2": 0.0, "u3": 0.0, "ur1": 0.0, "ur2": 0.0, "ur3": 0.0},
        "pinned": {"u1": 0.0, "u2": 0.0, "u3": 0.0, "ur1": None, "ur2": None, "ur3": None},
        "roller": {"u1": None, "u2": 0.0, "u3": 0.0, "ur1": None, "ur2": None, "ur3": None},
        "roller_x": {"u1": None, "u2": 0.0, "u3": 0.0, "ur1": None, "ur2": None, "ur3": None},
        "roller_y": {"u1": 0.0, "u2": None, "u3": 0.0, "ur1": None, "ur2": None, "ur3": None},
        "vertical": {"u1": None, "u2": None, "u3": 0.0, "ur1": None, "ur2": None, "ur3": None},
    }

    def plan(self, state: ModelProductionState) -> ModelProductionState:
        supports = []
        for support in state.semantic.supports:
            support_type = support.support_type.lower()
            dofs = self.DOF_MAP.get(support_type)
            if dofs is None:
                state.note("BoundaryAgent", f"Unknown support type '{support_type}' at {support.name}; using roller.", "warning")
                dofs = self.DOF_MAP["roller"]
                support_type = "roller"
            supports.append({"name": support.name, "x_m": support.x_m, "support_type": support_type, "dofs": dofs})
        state.model_plan["supports"] = supports
        state.note("BoundaryAgent", f"Translated {len(supports)} supports into Abaqus displacement BC definitions.")
        return state

