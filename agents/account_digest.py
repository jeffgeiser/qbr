"""
Account Digest Agent - Periodic summary pushed to Microsoft Teams.

Aggregates changes across a user's accounts (new cases, pipeline
movement, activity) and posts a formatted digest to their configured
Teams channel via incoming webhook.
"""

import logging
from core.agent_runtime import BaseAgent, AgentBlueprint
from core.models import AgentContext, AgentResult, InsightCard, Priority
from integrations.hub import hub

logger = logging.getLogger(__name__)


class AccountDigestAgent(BaseAgent):

    blueprint = AgentBlueprint(
        id="account_digest",
        name="Account Digest",
        description="Sends a periodic summary of account changes to your Microsoft Teams channel. Configure your webhook URL to start receiving digests.",
        category="intelligence",
        icon="inbox",
        color="teal",
        required_integrations=["salesforce"],
        default_config={
            "teams_webhook_url": "",
            "include_cases": True,
            "include_pipeline": True,
            "include_activities": True,
            "period_label": "Weekly",
        },
        capabilities=["digest", "notifications", "teams_integration"],
        schedule_options=["manual", "daily", "weekly"],
    )

    async def run(self, context: AgentContext) -> AgentResult:
        insights: list[InsightCard] = []
        errors: list[str] = []
        account_summaries: list[dict] = []

        webhook_url = context.config.get("teams_webhook_url", "")
        period = context.config.get("period_label", "Weekly")

        for account_name in context.account_names:
            try:
                summary = await self._summarize_account(account_name, context)
                if summary and summary.get("has_changes"):
                    account_summaries.append(summary)
            except Exception as e:
                errors.append(f"Digest failed for {account_name}: {e}")
                logger.error(f"AccountDigest error: {e}", exc_info=True)

        if account_summaries:
            insights.append(InsightCard(
                agent_instance_id=context.instance_id,
                agent_blueprint_id=self.blueprint.id,
                account_name="Portfolio",
                priority=Priority.INFO,
                title=f"{period} digest: {len(account_summaries)} account{'s' if len(account_summaries) != 1 else ''} with updates",
                summary=self._build_summary_text(account_summaries),
                detail={"accounts": account_summaries, "period": period},
                actions=[],
            ))

            if webhook_url:
                sent = await self._push_to_teams(webhook_url, period, account_summaries)
                if sent:
                    insights[-1].summary += " (sent to Teams)"
                else:
                    errors.append("Failed to send Teams notification")
            else:
                insights[-1].summary += " — configure a Teams webhook URL to receive notifications"

        return AgentResult(success=len(errors) == 0, insights=insights, errors=errors)

    async def _summarize_account(self, account_name: str, ctx: AgentContext) -> dict | None:
        days = ctx.time_range_days
        params = {"account_name": account_name, "days": days}

        summary = {"name": account_name, "has_changes": False}

        if ctx.config.get("include_cases", True):
            cases = await hub.query("cases", params, "salesforce")
            if cases.records:
                open_cases = [c for c in cases.records
                              if c.get("Status", "").lower() not in ("closed", "resolved")]
                critical = [c for c in open_cases
                            if c.get("Priority", "").lower() in ("critical", "high")]
                summary["new_cases"] = len(cases.records)
                summary["open_cases"] = len(open_cases)
                summary["has_changes"] = True
                if critical:
                    summary["alert"] = f"{len(critical)} critical/high cases"
                    summary["health"] = "Needs attention"
                else:
                    summary["health"] = "Normal"

        if ctx.config.get("include_pipeline", True):
            opps = await hub.query("opportunities", {"account_name": account_name, "status": "open"}, "salesforce")
            if opps.records:
                summary["pipeline_deals"] = len(opps.records)
                summary["has_changes"] = True

        if ctx.config.get("include_activities", True):
            activities = await hub.query("activities", params, "salesforce")
            if activities.records:
                summary["activities"] = len(activities.records)
                summary["has_changes"] = True

        return summary

    def _build_summary_text(self, summaries: list[dict]) -> str:
        parts = []
        for s in summaries[:5]:
            flags = []
            if s.get("alert"):
                flags.append(s["alert"])
            if s.get("new_cases"):
                flags.append(f"{s['new_cases']} cases")
            if s.get("pipeline_deals"):
                flags.append(f"{s['pipeline_deals']} deals")
            parts.append(f"{s['name']}: {', '.join(flags)}")
        text = "; ".join(parts)
        if len(summaries) > 5:
            text += f" (+{len(summaries) - 5} more)"
        return text

    async def _push_to_teams(self, webhook_url: str, period: str,
                             summaries: list[dict]) -> bool:
        from integrations.teams_webhook import send_teams_message, format_digest_card
        title, summary, sections = format_digest_card("", period, summaries)
        return await send_teams_message(webhook_url, title, summary, sections)
