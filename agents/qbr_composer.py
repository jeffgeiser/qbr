"""
QBR Composer Agent - wraps the existing briefing generator into the agent framework.

Generates Internal Health Briefs and Customer-Facing QBRs using LLM tool-use
orchestration over Salesforce data. This preserves full backward compatibility
with the existing /api/briefings/generate endpoint while also being invocable
as an agent from the command bar and workflow canvas.
"""

import json
import logging
from typing import AsyncGenerator

from core.agent_runtime import BaseAgent, AgentBlueprint
from core.models import AgentContext, AgentResult, InsightCard, Priority

logger = logging.getLogger(__name__)


class QBRComposerAgent(BaseAgent):

    blueprint = AgentBlueprint(
        id="qbr_composer",
        name="QBR Composer",
        description="Generates comprehensive Internal Health Briefs and Customer-Facing QBRs using live Salesforce data and AI synthesis.",
        category="composition",
        icon="document",
        color="indigo",
        required_integrations=["salesforce"],
        default_config={
            "briefing_type": "internal",
            "time_range_days": 90,
        },
        capabilities=["briefing_generation", "document_composition", "executive_summary"],
        schedule_options=["manual"],
    )

    async def run(self, context: AgentContext) -> AgentResult:
        """Run the QBR composer for each account in context."""
        insights: list[InsightCard] = []
        errors: list[str] = []
        briefing_type = context.config.get("briefing_type", "internal")

        for account_name in context.account_names:
            try:
                user_msg = context.user_message or f"{account_name} for the last {context.time_range_days} days"
                result_data = await self._generate_briefing(briefing_type, user_msg)

                if result_data:
                    insights.append(InsightCard(
                        agent_instance_id=context.instance_id,
                        agent_blueprint_id=self.blueprint.id,
                        account_name=account_name,
                        priority=Priority.INFO,
                        title=f"{'Internal Brief' if briefing_type == 'internal' else 'Customer QBR'} ready",
                        summary=result_data.get("executive_snapshot",
                                                result_data.get("executive_summary", "Briefing generated.")),
                        detail=result_data,
                        actions=[
                            {"label": "View Briefing", "action_type": "view_briefing",
                             "params": {"account_name": account_name, "type": briefing_type}},
                        ],
                    ))
                else:
                    errors.append(f"No briefing produced for {account_name}")
            except Exception as e:
                errors.append(f"Briefing generation failed for {account_name}: {e}")
                logger.error(f"QBRComposer error: {e}", exc_info=True)

        return AgentResult(success=len(errors) == 0, insights=insights, errors=errors)

    async def stream_generation(self, briefing_type: str, user_message: str) -> AsyncGenerator[str, None]:
        """Delegate to the existing briefing_generator for SSE streaming.
        This preserves backward compatibility with the /api/briefings/generate endpoint."""
        from services.briefing_generator import generate_briefing_stream
        async for event in generate_briefing_stream(briefing_type, user_message):
            yield event

    async def _generate_briefing(self, briefing_type: str, user_message: str) -> dict | None:
        """Non-streaming briefing generation. Collects all events and returns the final result."""
        from services.briefing_generator import generate_briefing_stream
        result_data = None
        async for event_str in generate_briefing_stream(briefing_type, user_message):
            if "briefing_ready" in event_str:
                try:
                    data_line = event_str.split("data: ", 1)[1].strip()
                    event = json.loads(data_line)
                    if event.get("type") == "briefing_ready":
                        from main import get_briefing_result
                        result = get_briefing_result(event["result_id"])
                        if result:
                            result_data = result["result"]
                except (json.JSONDecodeError, IndexError, KeyError):
                    pass
        return result_data
