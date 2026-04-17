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
            ))

        # Push to Teams if configured
        webhook_url = context.config.get("teams_webhook_url", "")
        if webhook_url:
            await self._push_to_teams(webhook_url, portfolio_stats, insights)

        return AgentResult(success=len(errors) == 0, insights=insights, errors=errors)

    async def _push_to_teams(self, webhook_url: str, stats: dict,
                             insights: list[InsightCard]):
        try:
            from integrations.teams_webhook import send_teams_message, format_executive_card

            metrics = {
                "Total Accounts": stats["total_accounts"],
                "Health (G/Y/R)": f"{stats['health'].get('green', 0)} / {stats['health'].get('yellow', 0)} / {stats['health'].get('red', 0)}",
                "Active Pipeline Deals": stats["total_pipeline_deals"],
            }

            highlights = [i.title for i in insights if i.priority == Priority.INFO]
            risks = [i.title for i in insights if i.priority in (Priority.HIGH, Priority.CRITICAL)]

            title, summary, sections = format_executive_card(
                "Executive Portfolio Pulse", metrics, highlights, risks
            )
            await send_teams_message(webhook_url, title, summary, sections, theme_color="5B5FC7")
        except Exception as e:
            logger.error(f"Executive Teams push failed: {e}")
