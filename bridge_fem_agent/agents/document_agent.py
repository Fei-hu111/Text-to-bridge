"""Load structured bridge semantics from JSON.

Future OCR/CAD/PDF parsing can feed the same semantic model.
"""

from __future__ import annotations

from pathlib import Path

from bridge_fem_agent.agents.base import ModelProductionState
from bridge_fem_agent.semantic.bridge_model import BridgeSemanticModel


class DocumentAgent:
    """Convert a structured JSON document into the semantic bridge model."""

    def load(self, input_path: Path) -> ModelProductionState:
        semantic = BridgeSemanticModel.from_json(input_path)
        state = ModelProductionState(semantic=semantic)
        state.note("DocumentAgent", f"Loaded semantic bridge model '{semantic.project_name}' from {input_path}.")
        # TODO: add drawing/PDF/CAD text extraction agent before semantic validation.
        return state

