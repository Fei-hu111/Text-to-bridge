"""Material and section planning agent."""

from __future__ import annotations

from bridge_fem_agent.agents.base import ModelProductionState


class MaterialAgent:
    """Prepare Abaqus material and beam-section definitions."""

    def plan(self, state: ModelProductionState) -> ModelProductionState:
        model = state.semantic
        material = next(iter(model.materials.values()))
        section = model.section
        state.model_plan["materials"] = {
            "primary_material": material.name,
            "materials": {name: spec.__dict__ for name, spec in model.materials.items()},
        }
        state.model_plan["section"] = {
            "name": section.name,
            "type": section.section_type,
            "width_m": section.width_m,
            "height_m": section.height_m,
            "profile": "RectangularProfile",
        }
        state.note("MaterialAgent", f"Assigned material {material.name} to section {section.name}.")
        return state

