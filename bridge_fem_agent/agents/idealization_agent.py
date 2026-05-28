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
        if model_level != "beam":
            state.note("IdealizationAgent", "First V2 generator emits a beam CAE model; requested level is recorded for future expansion.", "warning")
        state.model_plan["idealization"] = {
            "selected_model_level": "beam",
            "requested_model_level": requested,
            "element_type": model.mesh.element_type or "B31",
            "reason": "Samples emphasize wire/beam bridge models and beam models are reviewable for global bridge behaviour.",
        }
        state.note("IdealizationAgent", "Selected B31 beam idealization for reviewable global bridge model.")
        # TODO: add LLM-assisted choice between beam/shell/solid/mixed idealizations.
        return state

