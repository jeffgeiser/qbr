"""
Agent Runtime - core execution engine for the agentic platform.

Manages agent registration, instance lifecycle, and execution scheduling.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncGenerator, Optional
from datetime import datetime
import uuid
import json
import logging

from core.models import (
    AgentContext, AgentResult, InsightCard, AgentInstanceStatus, Priority,
)

logger = logging.getLogger(__name__)


@dataclass
class AgentBlueprint:
    """Definition of an agent type available in the registry."""
    id: str
    name: str
    description: str
    category: str  # "intelligence", "preparation", "strategy", "composition"
    icon: str = ""
    color: str = "blue"
    required_integrations: list[str] = field(default_factory=list)
    default_config: dict = field(default_factory=dict)
    capabilities: list[str] = field(default_factory=list)
    schedule_options: list[str] = field(default_factory=lambda: ["manual", "daily", "weekly"])

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "icon": self.icon,
            "color": self.color,
            "required_integrations": self.required_integrations,
            "default_config": self.default_config,
            "capabilities": self.capabilities,
            "schedule_options": self.schedule_options,
        }


class BaseAgent(ABC):
    """Base class for all agents."""

    blueprint: AgentBlueprint

    @abstractmethod
    async def run(self, context: AgentContext) -> AgentResult:
        pass

    async def stream(self, context: AgentContext) -> AsyncGenerator[dict, None]:
        """Stream execution events for real-time UI updates."""
        yield {"type": "status", "message": f"Running {self.blueprint.name}..."}
        result = await self.run(context)
        for insight in result.insights:
            yield {"type": "insight", "data": insight.to_dict()}
        if result.errors:
            for err in result.errors:
                yield {"type": "error", "message": err}
        yield {"type": "complete", "success": result.success, "insight_count": len(result.insights)}


@dataclass
class AgentInstance:
    """A user-activated instance of an agent blueprint."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = "default"
    blueprint_id: str = ""
    name: str = ""
    config: dict = field(default_factory=dict)
    scope: dict = field(default_factory=dict)
    schedule: str = "manual"
    status: AgentInstanceStatus = AgentInstanceStatus.ACTIVE
    last_run_at: str = ""
    next_run_at: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    insight_count: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "blueprint_id": self.blueprint_id,
            "name": self.name,
            "config": self.config,
            "scope": self.scope,
            "schedule": self.schedule,
            "status": self.status.value if isinstance(self.status, AgentInstanceStatus) else self.status,
            "last_run_at": self.last_run_at,
            "next_run_at": self.next_run_at,
            "created_at": self.created_at,
            "insight_count": self.insight_count,
        }


class AgentRegistry:
    """Registry of available agent blueprints and their implementations."""

    def __init__(self):
        self._blueprints: dict[str, AgentBlueprint] = {}
        self._implementations: dict[str, type[BaseAgent]] = {}

    def register(self, agent_class: type[BaseAgent]):
        bp = agent_class.blueprint
        self._blueprints[bp.id] = bp
        self._implementations[bp.id] = agent_class
        logger.info(f"Registered agent: {bp.name} ({bp.id})")

    def get_blueprint(self, blueprint_id: str) -> Optional[AgentBlueprint]:
        return self._blueprints.get(blueprint_id)

    def get_all_blueprints(self) -> list[AgentBlueprint]:
        return list(self._blueprints.values())

    def create_agent(self, blueprint_id: str) -> Optional[BaseAgent]:
        cls = self._implementations.get(blueprint_id)
        return cls() if cls else None


registry = AgentRegistry()
