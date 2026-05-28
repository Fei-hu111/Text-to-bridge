"""Pre-Abaqus model QA/QC agent."""

from __future__ import annotations

from bridge_fem_agent.agents.base import AgentMessage, ModelProductionState


class QaAgent:
    """Check semantic and planned model consistency before Abaqus generation."""

    def review(self, state: ModelProductionState) -> ModelProductionState:
        model = state.semantic
        findings: list[AgentMessage] = []
        if model.total_length_m <= 0.0:
            findings.append(AgentMessage("QaAgent", "error", "Total bridge length is not positive."))
        if not model.supports:
            findings.append(AgentMessage("QaAgent", "error", "At least one support is required."))
        if not any(abs(support.x_m) < 1e-6 for support in model.supports):
            findings.append(AgentMessage("QaAgent", "warning", "No support was found at the left end x=0."))
        if not any(abs(support.x_m - model.total_length_m) < 1e-6 for support in model.supports):
            findings.append(AgentMessage("QaAgent", "warning", "No support was found at the right end."))
        if not model.materials:
            findings.append(AgentMessage("QaAgent", "error", "No material definitions were provided."))
        if not state.model_plan.get("loads"):
            findings.append(AgentMessage("QaAgent", "warning", "No load definitions were prepared."))
        if state.model_plan.get("mesh", {}).get("target_size_m", 0.0) <= 0.0:
            findings.append(AgentMessage("QaAgent", "error", "Mesh target size is not positive."))

        state.qa_findings = findings
        if findings:
            for finding in findings:
                state.note("QaAgent", finding.message, finding.level)
        else:
            state.note("QaAgent", "Pre-generation QA passed with no findings.")
        return state

