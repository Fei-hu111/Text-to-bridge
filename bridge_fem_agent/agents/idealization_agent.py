"""Finite element idealization agent."""

from __future__ import annotations

from bridge_fem_agent.agents.base import ModelProductionState


class IdealizationAgent:
    """Choose a deterministic modelling level informed by samples and semantics."""

    def plan(self, state: ModelProductionState) -> ModelProductionState:
        model = state.semantic
        requested = model.model_level
        if requested == "auto":
            dominant = state.reference_patterns.get("dominant_style")
            model_level = "beam" if dominant in {None, "wire_beam"} else "solid"
        else:
            model_level = requested
        if model_level not in {"beam", "shell", "solid"}:
            state.note("IdealizationAgent", f"Unsupported model_level '{model_level}', falling back to beam.", "warning")
            model_level = "beam"
        element_type = model.mesh.element_type or ("C3D8R" if model_level == "solid" else "B31")
        if model_level == "solid" and element_type.upper() == "B31":
            element_type = "C3D8R"
        state.model_plan["idealization"] = {
            "selected_model_level": model_level,
            "requested_model_level": requested,
            "element_type": element_type,
            "reason": "Requested model level is honored; samples provide both wire/beam and solid-extrude modelling patterns.",
        }
        state.note("IdealizationAgent", f"Selected {model_level} idealization with {element_type} elements.")
        # TODO: add LLM-assisted choice between beam/shell/solid/mixed idealizations.
        return state
