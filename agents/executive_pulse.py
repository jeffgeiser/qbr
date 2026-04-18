"""
Executive Pulse Agent - Portfolio-wide health for leadership.

Designed for EVP/VP of Sales. Aggregates across ALL accounts to surface:
- Portfolio health distribution (green/yellow/red)
- Tier 1 accounts needing attention
- Team engagement gaps (accounts with no recent activity)
- Aggregate pipeline risk
- Exception-only reporting (only surfaces what needs exec attention)

Optionally pushes to a Teams webhook for async delivery.
"""

import os
import logging
from core.agent_runtime import BaseAgent, AgentBlueprint
from core.models import AgentContext, AgentResult, InsightCard, Priority
from integrations.hub import hub

logger = logging.getLogger(__name__)


class ExecutivePulseAgent(BaseAgent):

    blueprint = AgentBlueprint(
        id="executive_pulse",
        name="Executive Pulse",
        description="Portfolio-wide health summary for leadership. Aggregates risk signals, engagement gaps, and pipeline status across all accounts. Exception-only reporting.",
        category="intelligence",
        icon="briefcase",
        color="slate",
        required_integrations=["salesforce"],
        default_config={
            "teams_webhook_url": "",
            "focus_tiers": ["Tier 1", "Tier 2"],
            "engagement_gap_days": 30,
        },
        capabilities=["executive_summary", "portfolio_health", "team_oversight"],
        schedule_options=["manual", "daily", "weekly"],
        data_sources=[
            "Local accounts database (health, tier, owner for all accounts)",
            "Salesforce Cases (critical case counts per account)",
            "Salesforce Open Opportunities (pipeline deal counts)",
            "Salesforce Closed-Lost Opportunities (loss trends)",
            "Salesforce Activities (engagement gaps per account)",
        ],
        logic_steps=[
            "Sweeps ALL accounts in focus tiers (default: Tier 1 + Tier 2)",
            "Aggregates health distribution: green/yellow/red counts",
            "Identifies accounts with open critical/high cases",
            "Flags Tier 1 accounts with no recent engagement (owner named)",
            "Counts lost deals across portfolio for trend detection",
            "Generates exception-only insights (only surfaces what needs attention)",
            "Optionally pushes executive summary to Teams webhook",
        ],
        output_types=["Portfolio health overview", "Critical case alerts", "Engagement gap reports", "Loss trend alerts"],
    )

    async def run(self, context: AgentContext) -> AgentResult:
        insights: list[InsightCard] = []
        errors: list[str] = []

        try:
            from main import get_all_accounts
            all_accounts = get_all_accounts()
        except Exception as e:
            return AgentResult(success=False, errors=[f"Could not load accounts: {e}"])

        focus_tiers = context.config.get("focus_tiers", ["Tier 1", "Tier 2"])
        focus_accounts = [a for a in all_accounts if a["tier"] in focus_tiers]

        portfolio_stats = {
            "total_accounts": len(focus_accounts),
            "health": {"green": 0, "yellow": 0, "red": 0},
            "tier_breakdown": {},
            "accounts_with_critical_cases": [],
            "accounts_with_no_activity": [],
            "total_pipeline_deals": 0,
            "accounts_with_lost_deals": [],
        }

        for account in focus_accounts:
            name = account["name"]
            tier = account["tier"]
            health = account.get("healthSentiment", "green")
            portfolio_stats["health"][health] = portfolio_stats["health"].get(health, 0) + 1
            portfolio_stats["tier_breakdown"].setdefault(tier, 0)
            portfolio_stats["tier_breakdown"][tier] += 1

            try:
                params = {"account_name": name, "days": context.time_range_days}

                cases = await hub.query("cases", params, "salesforce")
                if cases.records:
                    critical = [c for c in cases.records
                                if c.get("Priority", "").lower() in ("critical", "high")
                                and c.get("Status", "").lower() not in ("closed", "resolved")]
                    if critical:
                        portfolio_stats["accounts_with_critical_cases"].append({
                            "name": name, "tier": tier, "critical_count": len(critical),
                        })

                opps = await hub.query("opportunities",
                                       {"account_name": name, "status": "open"}, "salesforce")
                if opps.records:
                    portfolio_stats["total_pipeline_deals"] += len(opps.records)

                lost = await hub.query("opportunities",
                                       {"account_name": name, "status": "lost",
                                        "days": context.time_range_days}, "salesforce")
                if lost.records:
                    portfolio_stats["accounts_with_lost_deals"].append({
                        "name": name, "tier": tier, "lost_count": len(lost.records),
                    })

                activities = await hub.query("activities", params, "salesforce")
                if not activities.records or len(activities.records) < 2:
                    portfolio_stats["accounts_with_no_activity"].append({
                        "name": name, "tier": tier, "owner": account.get("owner", ""),
                    })

            except Exception as e:
                logger.warning(f"Executive pulse skipping {name}: {e}")

        # --- Generate executive insights ---

        # Portfolio health overview
        h = portfolio_stats["health"]
        insights.append(InsightCard(
            agent_instance_id=context.instance_id,
            agent_blueprint_id=self.blueprint.id,
            account_name="All Accounts",
            priority=Priority.INFO if h.get("red", 0) == 0 else Priority.HIGH,
            title=f"Portfolio: {h.get('green', 0)} healthy, {h.get('yellow', 0)} caution, {h.get('red', 0)} at risk",
            summary=f"{portfolio_stats['total_accounts']} accounts tracked across {len(portfolio_stats['tier_breakdown'])} tiers. {portfolio_stats['total_pipeline_deals']} active pipeline deals.",
            detail=portfolio_stats,
            actions=[],
            logic_explanation=f"Aggregated health data across all {portfolio_stats['total_accounts']} accounts in focus tiers ({', '.join(focus_tiers)}). Each account's healthSentiment field was read from the local accounts database and categorized as green/yellow/red. Salesforce Cases, Opportunities, Activities, and Closed-Lost Opportunities were queried per account over the last {context.time_range_days} days to build the full portfolio picture.",
        ))

        # Critical case exceptions
        critical_accts = portfolio_stats["accounts_with_critical_cases"]
        if critical_accts:
            critical_accts.sort(key=lambda x: x["critical_count"], reverse=True)
            insights.append(InsightCard(
                agent_instance_id=context.instance_id,
                agent_blueprint_id=self.blueprint.id,
                account_name="All Accounts",
                priority=Priority.HIGH,
                title=f"{len(critical_accts)} account{'s' if len(critical_accts) != 1 else ''} with critical support cases",
                summary="; ".join(f"{a['name']} ({a['critical_count']})" for a in critical_accts[:5]),
                detail={"accounts": critical_accts},
                actions=[],
                logic_explanation=f"For each of the {portfolio_stats['total_accounts']} accounts in focus tiers ({', '.join(focus_tiers)}), queried Salesforce Cases over the last {context.time_range_days} days. Filtered for cases where Priority is 'Critical' or 'High' AND Status is not 'Closed' or 'Resolved'. {len(critical_accts)} account(s) had at least one matching case.",
            ))

        # Engagement gaps — accounts no one is touching
        inactive = portfolio_stats["accounts_with_no_activity"]
        tier1_inactive = [a for a in inactive if a["tier"] == "Tier 1"]
        if tier1_inactive:
            insights.append(InsightCard(
                agent_instance_id=context.instance_id,
                agent_blueprint_id=self.blueprint.id,
                account_name="All Accounts",
                priority=Priority.HIGH,
                title=f"{len(tier1_inactive)} Tier 1 account{'s' if len(tier1_inactive) != 1 else ''} with no recent engagement",
                summary="; ".join(f"{a['name']} (owner: {a['owner']})" for a in tier1_inactive),
                detail={"inactive_tier1": tier1_inactive, "all_inactive": inactive},
                actions=[],
                logic_explanation=f"Queried Salesforce Activities for each Tier 1 account over the last {context.time_range_days} days. Accounts with fewer than 2 activity records are flagged as having no recent engagement. {len(tier1_inactive)} Tier 1 account(s) fell below this threshold. This is elevated to High priority because Tier 1 accounts are your most strategic customers.",
            ))
        elif inactive:
            insights.append(InsightCard(
                agent_instance_id=context.instance_id,
                agent_blueprint_id=self.blueprint.id,
                account_name="All Accounts",
                priority=Priority.MEDIUM,
                title=f"{len(inactive)} account{'s' if len(inactive) != 1 else ''} with low engagement",
                summary="; ".join(f"{a['name']}" for a in inactive[:5]),
                detail={"inactive": inactive},
                actions=[],
                logic_explanation=f"Queried Salesforce Activities for each account in focus tiers ({', '.join(focus_tiers)}) over the last {context.time_range_days} days. Accounts with fewer than 2 activity records are flagged as having low engagement. {len(inactive)} non-Tier 1 account(s) fell below this threshold. No Tier 1 accounts were affected, so this is reported at Medium priority.",
            ))

        # Lost deal trend
        lost_accts = portfolio_stats["accounts_with_lost_deals"]
        if lost_accts:
            total_lost = sum(a["lost_count"] for a in lost_accts)
            insights.append(InsightCard(
                agent_instance_id=context.instance_id,
                agent_blueprint_id=self.blueprint.id,
                account_name="All Accounts",
                priority=Priority.MEDIUM,
                title=f"{total_lost} deal{'s' if total_lost != 1 else ''} lost across {len(lost_accts)} account{'s' if len(lost_accts) != 1 else ''}",
                summary="; ".join(f"{a['name']} ({a['lost_count']} lost)" for a in lost_accts[:5]),
                detail={"accounts_with_losses": lost_accts},
                actions=[],
                logic_explanation=f"Queried Salesforce Opportunities with status 'Closed Lost' for each account in focus tiers ({', '.join(focus_tiers)}) over the last {context.time_range_days} days. {len(lost_accts)} account(s) had at least one closed-lost deal, totaling {total_lost} lost deal(s) across the portfolio.",
            ))

        # Push to Teams if configured
        webhook_url = context.config.get("teams_webhook_url", "")
        if webhook_url:
            await self._push_to_teams(webhook_url, portfolio_stats, insights)

        return AgentResult(success=len(errors) == 0, insights=insights, errors=errors)

    async def _push_to_teams(self, webhook_url: str, stats: dict,
                             insights: list[InsightCard]):
        try:
            from integrations.teams_webhook import send_teams_message

            metrics_facts = [
                {"name": "Total Accounts", "value": str(stats["total_accounts"])},
                {"name": "Health (G/Y/R)", "value": f"{stats['health'].get('green', 0)} / {stats['health'].get('yellow', 0)} / {stats['health'].get('red', 0)}"},
                {"name": "Active Pipeline Deals", "value": str(stats["total_pipeline_deals"])},
            ]

            sections = [
                {"activityTitle": "Portfolio Metrics", "facts": metrics_facts, "markdown": True},
            ]

            # Build detailed risk sections with account names and owners
            critical_accts = stats.get("accounts_with_critical_cases", [])
            if critical_accts:
                lines = [f"**{a['name']}** ({a['tier']}) — {a['critical_count']} critical case{'s' if a['critical_count'] != 1 else ''}" for a in critical_accts[:8]]
                sections.append({
                    "activityTitle": f"Support Escalation Risk — {len(critical_accts)} Account{'s' if len(critical_accts) != 1 else ''}",
                    "text": "\n\n".join(lines),
                    "markdown": True,
                })

            inactive = stats.get("accounts_with_no_activity", [])
            tier1_inactive = [a for a in inactive if a["tier"] == "Tier 1"]
            if tier1_inactive:
                lines = [f"**{a['name']}** — owner: {a.get('owner', 'unassigned')}" for a in tier1_inactive[:10]]
                sections.append({
                    "activityTitle": f"Tier 1 Engagement Gaps — {len(tier1_inactive)} Account{'s' if len(tier1_inactive) != 1 else ''}",
                    "text": "\n\n".join(lines),
                    "markdown": True,
                })

            lost_accts = stats.get("accounts_with_lost_deals", [])
            if lost_accts:
                total_lost = sum(a["lost_count"] for a in lost_accts)
                lines = [f"**{a['name']}** — {a['lost_count']} deal{'s' if a['lost_count'] != 1 else ''} lost" for a in lost_accts[:8]]
                sections.append({
                    "activityTitle": f"Lost Deals — {total_lost} Across {len(lost_accts)} Account{'s' if len(lost_accts) != 1 else ''}",
                    "text": "\n\n".join(lines),
                    "markdown": True,
                })

            # Link back to workbench
            workbench_url = os.environ.get("APP_BASE_URL", "")
            if workbench_url:
                sections.append({
                    "text": f"[Open Agent Workbench]({workbench_url}/qbr/workbench)",
                    "markdown": True,
                })

            summary = f"{stats['total_accounts']} accounts — {stats['health'].get('red', 0)} at risk"
            await send_teams_message(webhook_url, "Executive Portfolio Pulse", summary, sections, theme_color="5B5FC7")
        except Exception as e:
            logger.error(f"Executive Teams push failed: {e}")
