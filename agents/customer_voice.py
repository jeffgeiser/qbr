"""
Customer Voice Agent - Synthesizes support patterns into account narrative.

Analyzes case volume, severity trends, resolution times, and recurring
themes to surface product/service feedback and predict escalations.
"""

import logging

from core.agent_runtime import BaseAgent, AgentBlueprint
from core.models import AgentContext, AgentResult, InsightCard, Priority
from integrations.hub import hub

logger = logging.getLogger(__name__)


class CustomerVoiceAgent(BaseAgent):

    blueprint = AgentBlueprint(
        id="customer_voice",
        name="Customer Voice",
        description="Synthesizes support ticket patterns into account narrative. Detects escalation risks, recurring issues, and feature request signals.",
        category="intelligence",
        icon="chat",
        color="violet",
        required_integrations=["salesforce"],
        default_config={
            "escalation_threshold": 3,
            "trend_window_days": 30,
        },
        capabilities=["support_analysis", "escalation_prediction", "feedback_synthesis"],
        schedule_options=["manual", "daily", "weekly"],
    )

    async def run(self, context: AgentContext) -> AgentResult:
        insights: list[InsightCard] = []
        errors: list[str] = []

        for account_name in context.account_names:
            try:
                cards = await self._analyze_support(account_name, context)
                if account_name.lower() in [n.lower() for n in context.must_win_accounts]:
                    for c in cards:
                        if c.priority == Priority.MEDIUM:
                            c.priority = Priority.HIGH
                insights.extend(cards)
            except Exception as e:
                errors.append(f"Support analysis failed for {account_name}: {e}")
                logger.error(f"CustomerVoice error: {e}", exc_info=True)

        return AgentResult(success=len(errors) == 0, insights=insights, errors=errors)

    async def _analyze_support(self, account_name: str, ctx: AgentContext) -> list[InsightCard]:
        insights: list[InsightCard] = []
        days = ctx.time_range_days
        params = {"account_name": account_name, "days": days}

        cases = await hub.query("cases", params, "salesforce")

        if not cases.records:
            return insights

        total = len(cases.records)
        open_cases = [c for c in cases.records
                      if c.get("Status", "").lower() not in ("closed", "resolved")]
        closed_cases = [c for c in cases.records
                        if c.get("Status", "").lower() in ("closed", "resolved")]
        critical = [c for c in open_cases
                    if c.get("Priority", "").lower() in ("critical", "high")]

        # Escalation risk: many open critical cases
        if len(critical) >= ctx.config.get("escalation_threshold", 3):
            insights.append(InsightCard(
                agent_instance_id=ctx.instance_id,
                agent_blueprint_id=self.blueprint.id,
                account_name=account_name,
                priority=Priority.CRITICAL,
                title=f"Escalation risk: {len(critical)} critical cases",
                summary=f"{account_name} has {len(critical)} open critical/high cases out of {len(open_cases)} total open. This pattern often precedes executive escalation.",
                detail={
                    "critical_cases": critical[:5],
                    "total_open": len(open_cases),
                    "total_closed": len(closed_cases),
                },
                sources=cases.sources[:5],
                actions=[
                    {"label": "View Cases", "action_type": "source_link", "params": {}},
                    {"label": "Generate Health Brief", "action_type": "generate_briefing",
                     "params": {"account_name": account_name, "type": "internal"}},
                ],
            ))

        # High volume signal
        if total > 10:
            ratio = len(open_cases) / total if total > 0 else 0
            if ratio > 0.4:
                insights.append(InsightCard(
                    agent_instance_id=ctx.instance_id,
                    agent_blueprint_id=self.blueprint.id,
                    account_name=account_name,
                    priority=Priority.MEDIUM,
                    title=f"Support backlog growing: {len(open_cases)}/{total} cases open",
                    summary=f"{int(ratio * 100)}% of cases for {account_name} in the last {days} days are still open. Resolution rate may be declining.",
                    detail={
                        "open_count": len(open_cases),
                        "closed_count": len(closed_cases),
                        "open_ratio": round(ratio, 2),
                    },
                    sources=cases.sources[:3],
                    actions=[
                        {"label": "Run Health Brief", "action_type": "generate_briefing",
                         "params": {"account_name": account_name, "type": "internal"}},
                    ],
                ))

        # Subject clustering — detect recurring themes
        subjects = [c.get("Subject", "") for c in cases.records if c.get("Subject")]
        theme_counts = self._cluster_subjects(subjects)
        recurring = [(theme, count) for theme, count in theme_counts.items() if count >= 3]
        if recurring:
            recurring.sort(key=lambda x: x[1], reverse=True)
            insights.append(InsightCard(
                agent_instance_id=ctx.instance_id,
                agent_blueprint_id=self.blueprint.id,
                account_name=account_name,
                priority=Priority.MEDIUM,
                title=f"Recurring issue pattern: {recurring[0][0]}",
                summary=f"{account_name} has {len(recurring)} recurring support themes. Top: \"{recurring[0][0]}\" ({recurring[0][1]} cases). This may indicate a systemic product/service issue.",
                detail={"recurring_themes": [{"theme": t, "count": c} for t, c in recurring[:5]]},
                sources=cases.sources[:3],
                actions=[],
            ))

        if not insights:
            insights.append(InsightCard(
                agent_instance_id=ctx.instance_id,
                agent_blueprint_id=self.blueprint.id,
                account_name=account_name,
                priority=Priority.INFO,
                title="Support health normal",
                summary=f"{account_name}: {total} cases in {days} days, {len(open_cases)} open. No unusual patterns detected.",
                detail={"total": total, "open": len(open_cases), "closed": len(closed_cases)},
            ))

        return insights

    def _cluster_subjects(self, subjects: list[str]) -> dict[str, int]:
        """Simple keyword-based subject clustering."""
        keywords = {}
        noise = {"the", "a", "an", "is", "for", "to", "in", "on", "of", "and", "or", "not",
                 "with", "at", "from", "by", "this", "that", "it", "as", "be", "was", "are",
                 "case", "issue", "problem", "request", "ticket", "support", "help", "need",
                 "please", "zenlayer", "-", "re:", "fw:", ""}
        for subj in subjects:
            words = subj.lower().split()
            significant = [w.strip(".,!?()[]") for w in words if w.lower().strip(".,!?()[]") not in noise and len(w) > 2]
            for word in significant[:3]:
                keywords[word] = keywords.get(word, 0) + 1
        return keywords
