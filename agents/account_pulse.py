"""
Account Pulse Agent - Continuous health monitoring across accounts.

Fetches Salesforce data, detects risk signals, engagement gaps,
and pipeline anomalies. Emits prioritized InsightCards.
"""

import logging
from core.agent_runtime import BaseAgent, AgentBlueprint
from core.models import AgentContext, AgentResult, InsightCard, Priority
from integrations.hub import hub

logger = logging.getLogger(__name__)


class AccountPulseAgent(BaseAgent):

    blueprint = AgentBlueprint(
        id="account_pulse",
        name="Account Pulse",
        description="Continuous health monitoring across your accounts. Surfaces risk signals, engagement gaps, and pipeline changes proactively.",
        category="intelligence",
        icon="pulse",
        color="emerald",
        required_integrations=["salesforce"],
        default_config={
            "health_threshold": 3,
            "alert_on_critical_cases": True,
            "alert_on_pipeline_changes": True,
            "alert_on_engagement_gaps": True,
        },
        capabilities=["health_monitoring", "risk_detection", "trend_analysis"],
        schedule_options=["manual", "hourly", "daily", "weekly"],
    )

    async def run(self, context: AgentContext) -> AgentResult:
        insights: list[InsightCard] = []
        errors: list[str] = []

        for account_name in context.account_names:
            try:
                cards = await self._analyze_account(account_name, context)
                if account_name.lower() in [n.lower() for n in context.must_win_accounts]:
                    for c in cards:
                        if c.priority == Priority.MEDIUM:
                            c.priority = Priority.HIGH
                        elif c.priority == Priority.HIGH:
                            c.priority = Priority.CRITICAL
                insights.extend(cards)
            except Exception as e:
                errors.append(f"Failed to analyze {account_name}: {e}")
                logger.error(f"AccountPulse error for {account_name}: {e}", exc_info=True)

        return AgentResult(success=len(errors) == 0, insights=insights, errors=errors)

    async def _analyze_account(self, account_name: str, ctx: AgentContext) -> list[InsightCard]:
        insights: list[InsightCard] = []
        days = ctx.time_range_days
        params = {"account_name": account_name, "days": days}

        cases = await hub.query("cases", params, "salesforce")
        opps = await hub.query("opportunities", params, "salesforce")
        activities = await hub.query("activities", params, "salesforce")

        # --- Support health ---
        if cases.records:
            critical = [c for c in cases.records
                        if c.get("Priority", "").lower() in ("critical", "high")
                        and c.get("Status", "").lower() not in ("closed", "resolved")]
            if critical:
                insights.append(InsightCard(
                    agent_instance_id=ctx.instance_id,
                    agent_blueprint_id=self.blueprint.id,
                    account_name=account_name,
                    priority=Priority.HIGH,
                    title=f"{len(critical)} critical case{'s' if len(critical) != 1 else ''} open",
                    summary=f"{account_name} has {len(critical)} high/critical priority support cases requiring attention.",
                    detail={"critical_cases": critical[:5]},
                    sources=cases.sources[:5],
                    actions=[
                        {"label": "View in Salesforce", "action_type": "source_link", "params": {}},
                        {"label": "Generate Health Brief", "action_type": "generate_briefing",
                         "params": {"account_name": account_name, "type": "internal"}},
                    ],
                ))

            open_count = len([c for c in cases.records
                             if c.get("Status", "").lower() not in ("closed", "resolved")])
            closed_count = len(cases.records) - open_count
            if open_count > 5:
                insights.append(InsightCard(
                    agent_instance_id=ctx.instance_id,
                    agent_blueprint_id=self.blueprint.id,
                    account_name=account_name,
                    priority=Priority.MEDIUM,
                    title=f"High case volume: {open_count} open tickets",
                    summary=f"{account_name} has {open_count} open and {closed_count} closed cases in the last {days} days.",
                    detail={"open_count": open_count, "closed_count": closed_count},
                    sources=cases.sources[:3],
                    actions=[
                        {"label": "Run Health Brief", "action_type": "generate_briefing",
                         "params": {"account_name": account_name, "type": "internal"}},
                    ],
                ))

        # --- Pipeline health ---
        if opps.records:
            lost = [o for o in opps.records
                    if o.get("StageName", "").lower() in ("closed lost", "lost")]
            stalled = [o for o in opps.records
                       if o.get("StageName", "").lower() not in
                       ("closed won", "closed lost", "won", "lost")
                       and not o.get("NextStep")]

            if lost:
                insights.append(InsightCard(
                    agent_instance_id=ctx.instance_id,
                    agent_blueprint_id=self.blueprint.id,
                    account_name=account_name,
                    priority=Priority.HIGH,
                    title=f"{len(lost)} deal{'s' if len(lost) != 1 else ''} lost recently",
                    summary=f"{account_name} lost {len(lost)} opportunity(ies) in the last {days} days. Review for pattern or competitive displacement.",
                    detail={"lost_deals": lost[:5]},
                    sources=opps.sources[:5],
                    actions=[
                        {"label": "View Pipeline", "action_type": "source_link", "params": {}},
                    ],
                ))

            if stalled:
                insights.append(InsightCard(
                    agent_instance_id=ctx.instance_id,
                    agent_blueprint_id=self.blueprint.id,
                    account_name=account_name,
                    priority=Priority.MEDIUM,
                    title=f"{len(stalled)} stalled deal{'s' if len(stalled) != 1 else ''}",
                    summary=f"{account_name} has {len(stalled)} open opportunities with no defined next step.",
                    detail={"stalled_deals": stalled[:5]},
                    sources=opps.sources[:5],
                    actions=[
                        {"label": "View Pipeline", "action_type": "source_link", "params": {}},
                    ],
                ))

        # --- Engagement gaps ---
        if not activities.records or len(activities.records) < 2:
            insights.append(InsightCard(
                agent_instance_id=ctx.instance_id,
                agent_blueprint_id=self.blueprint.id,
                account_name=account_name,
                priority=Priority.MEDIUM,
                title="Low engagement detected",
                summary=f"{account_name} has very few recorded activities in the last {days} days. Consider scheduling outreach.",
                detail={"activity_count": len(activities.records) if activities.records else 0},
                sources=activities.sources,
                actions=[
                    {"label": "Prep Meeting", "action_type": "run_agent",
                     "params": {"agent": "meeting_prep", "account": account_name}},
                ],
            ))

        if not insights:
            insights.append(InsightCard(
                agent_instance_id=ctx.instance_id,
                agent_blueprint_id=self.blueprint.id,
                account_name=account_name,
                priority=Priority.INFO,
                title="Stable",
                summary=f"{account_name} shows no notable changes in the last {days} days.",
                detail={},
                sources=[],
                actions=[],
            ))

        return insights
