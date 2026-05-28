"""Load planning agent."""

from __future__ import annotations

from bridge_fem_agent.agents.base import ModelProductionState


class LoadAgent:
    """Convert bridge loads into Abaqus-ready load definitions."""

    def plan(self, state: ModelProductionState) -> ModelProductionState:
        model = state.semantic
        model_level = state.model_plan.get("idealization", {}).get("selected_model_level", "beam")
        loads = []
        for load in model.loads:
            load_type = load.load_type.lower()
            if load_type == "gravity":
                loads.append({"type": "gravity", "name": load.name, "components": {"comp3": -9.81}})
            elif load_type in {"uniform", "uniform_deck_pressure", "deck_pressure"}:
                pressure = float(load.value or 0.0)
                line_load = pressure * model.deck_width_m
                if model_level == "solid":
                    loads.append({"type": "surface_pressure", "name": load.name, "pressure_pa": pressure, "target_surface": "DECK_TOP"})
                else:
                    loads.append({"type": "beam_line_load", "name": load.name, "pressure_pa": pressure, "line_load_n_m": line_load, "component": "comp3", "value": -line_load})
            elif load_type in {"point", "concentrated"}:
                loads.append({"type": "concentrated_force", "name": load.name, "value": float(load.value or 0.0), "direction": load.direction})
            else:
                state.note("LoadAgent", f"Load type '{load.load_type}' is recorded but not emitted in V2 beam script.", "warning")
                loads.append({"type": "unsupported", "name": load.name, "raw_type": load.load_type, "value": load.value})
        state.model_plan["loads"] = loads
        state.note("LoadAgent", f"Prepared {len(loads)} load definitions.")
        return state
