"""Common data structures for deterministic V2 agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bridge_fem_agent.semantic.bridge_model import BridgeSemanticModel


@dataclass(frozen=True)
class AgentMessage:
    agent: str
    level: str
    message: str


@dataclass
class ModelProductionState:
    semantic: BridgeSemanticModel
    reference_patterns: dict[str, Any] = field(default_factory=dict)
    model_plan: dict[str, Any] = field(default_factory=dict)
    qa_findings: list[AgentMessage] = field(default_factory=list)
    agent_messages: list[AgentMessage] = field(default_factory=list)

    def note(self, agent: str, message: str, level: str = "info") -> None:
        self.agent_messages.append(AgentMessage(agent=agent, level=level, message=message))

