"""Deterministic repair rules for common Abaqus input errors."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from bridge_fem_agent.diagnosis.error_classifier import DiagnosticIssue
from bridge_fem_agent.inp.inp_editor import InpEditor
from bridge_fem_agent.inp.inp_parser import InpSummary

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RepairAction:
    category: str
    description: str
    changed: bool


class RepairRules:
    """Apply narrow rule-based fixes that are safe to record and review."""

    def __init__(self) -> None:
        self.editor = InpEditor()

    def apply(self, summary: InpSummary, issues: list[DiagnosticIssue]) -> tuple[str, list[RepairAction]]:
        text = summary.text
        actions: list[RepairAction] = []
        categories = {issue.category for issue in issues}

        # Always run structural sanity rules; they are idempotent and help when
        # Abaqus reports a vague downstream error.
        for set_name in ("LEFT_SUPPORT", "RIGHT_SUPPORT"):
            before = text
            local_summary = InpSummary(summary.path, text, summary.nodes, summary.elements, summary.nsets, summary.elsets, summary.materials, summary.referenced_materials, summary.referenced_sets, summary.has_step)
            text = self.editor.ensure_required_nset(local_summary, set_name)
            actions.append(RepairAction("missing_set", f"Ensured node set {set_name}.", text != before))

        if "undefined_material" in categories or "unknown" in categories:
            before = text
            local_summary = InpSummary(summary.path, text, summary.nodes, summary.elements, summary.nsets, summary.elsets, summary.materials, summary.referenced_materials, summary.referenced_sets, summary.has_step)
            text = self.editor.ensure_default_material(local_summary)
            actions.append(RepairAction("undefined_material", "Ensured default CONCRETE material definition.", text != before))

        if "step_definition_error" in categories or "unknown" in categories:
            before = text
            local_summary = InpSummary(summary.path, text, summary.nodes, summary.elements, summary.nsets, summary.elsets, summary.materials, summary.referenced_materials, summary.referenced_sets, summary.has_step)
            text = self.editor.ensure_step(local_summary)
            actions.append(RepairAction("step_definition_error", "Ensured a static analysis step exists.", text != before))

        if "rigid_body_zero_pivot" in categories:
            before = text
            local_summary = InpSummary(summary.path, text, summary.nodes, summary.elements, summary.nsets, summary.elsets, summary.materials, summary.referenced_materials, summary.referenced_sets, summary.has_step)
            text = self.editor.stabilize_zero_pivot(local_summary)
            actions.append(RepairAction("rigid_body_zero_pivot", "Added minimal rotational restraint at LEFT_SUPPORT.", text != before))

        if "non_convergence" in categories:
            before = text
            text = self.editor.add_static_controls(text)
            actions.append(RepairAction("non_convergence", "Added conservative static controls.", text != before))

        # TODO: insert future LLM reasoning interface after deterministic rules.
        LOGGER.info("Repair rules produced %s actions.", len(actions))
        return text, [action for action in actions if action.changed]
