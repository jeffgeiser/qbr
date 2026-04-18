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
        data_sources=[
            "Salesforce Cases (open/closed, priority, status)",
            "Salesforce Open Opportunities (stage, amount, next step)",
            "Salesforce Closed-Won Opportunities (recent wins)",
            "Salesforce Closed-Lost Opportunities (recent losses)",
            "Salesforce Activities/Tasks (engagement volume)",
        ],
        logic_steps=[
            "Flags critical/high priority cases that are still open",
            "Alerts if more than 5 cases are open simultaneously",
            "Surfaces recent closed-won deals as positive momentum",
            "Flags recently lost deals for competitive review",
            "Identifies stalled deals (open with no defined next step)",
            "Detects engagement gaps (fewer than 2 activities in time range)",
            "Boosts priority for accounts marked as must-win",
        ],
        output_types=["Risk alerts", "Momentum signals", "Engagement warnings", "Stable status with evidence"],
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
        open_opps = await hub.query("opportunities", {"account_name": account_name, "status": "open"}, "salesforce")
        won_opps = await hub.query("opportunities", {"account_name": account_name, "status": "won", "days": days}, "salesforce")
        lost_opps = await hub.query("opportunities", {"account_name": account_name, "status": "lost", "days": days}, "salesforce")
        activities = await hub.query("activities", params, "salesforce")

        all_sources = ((cases.sources or []) + (open_opps.sources or []) +
                       (won_opps.sources or []) + (lost_opps.sources or []) +
                       (activities.sources or []))
        data_receipt = {
            "sources_checked": [
                "Salesforce Cases", "Salesforce Open Opportunities",
                "Salesforce Closed-Won", "Salesforce Closed-Lost",
                "Salesforce Activities",
            ],
            "cases_found": len(cases.records) if cases.records else 0,
            "open_opportunities": len(open_opps.records) if open_opps.records else 0,
            "closed_won": len(won_opps.records) if won_opps.records else 0,
            "closed_lost": len(lost_opps.records) if lost_opps.records else 0,
            "activities_found": len(activities.records) if activities.records else 0,
            "salesforce_connected": not bool(cases.error),
            "time_range_days": days,
        }

        case_open_count = 0
        case_closed_count = 0

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
                    detail={"critical_cases": critical[:5], "data_receipt": data_receipt},
                    sources=cases.sources[:5],
                    logic_explanation=f"Queried Salesforce Cases where Account.Name matches and CreatedDate is within the last {days} days. Filtered for cases with Priority = 'Critical' or 'High' AND Status is not 'Closed' or 'Resolved'. Found {len(critical)} matching cases.",
                    actions=[
                        {"label": "View in Salesforce", "action_type": "source_link", "params": {}},
                        {"label": "Generate Health Brief", "action_type": "generate_briefing",
                         "params": {"account_name": account_name, "type": "internal"}},
                    ],
                ))

            case_open_count = len([c for c in cases.records
                             if c.get("Status", "").lower() not in ("closed", "resolved")])
            case_closed_count = len(cases.records) - case_open_count
            if case_open_count > 5:
                insights.append(InsightCard(
                    agent_instance_id=ctx.instance_id,
                    agent_blueprint_id=self.blueprint.id,
                    account_name=account_name,
                    priority=Priority.MEDIUM,
                    title=f"High case volume: {case_open_count} open tickets",
                    summary=f"{account_name} has {case_open_count} open and {case_closed_count} closed cases in the last {days} days.",
                    detail={"open_count": case_open_count, "closed_count": case_closed_count, "data_receipt": data_receipt},
                    sources=cases.sources[:3],
                    logic_explanation=f"Queried all Salesforce Cases for this account in the last {days} days. Counted cases where Status is not 'Closed' or 'Resolved'. Threshold for this alert: more than 5 open cases. Found {case_open_count} open out of {len(cases.records)} total.",
                    actions=[
                        {"label": "Run Health Brief", "action_type": "generate_briefing",
                         "params": {"account_name": account_name, "type": "internal"}},
                    ],
                ))

        # --- Pipeline health & momentum ---
        open_deals = len(open_opps.records) if open_opps.records else 0
        won_deals = len(won_opps.records) if won_opps.records else 0
        lost_deals_count = len(lost_opps.records) if lost_opps.records else 0

        if won_deals > 0:
            insights.append(InsightCard(
                agent_instance_id=ctx.instance_id,
                agent_blueprint_id=self.blueprint.id,
                account_name=account_name,
                priority=Priority.INFO,
                title=f"{won_deals} deal{'s' if won_deals != 1 else ''} closed-won recently",
                summary=f"{account_name} closed {won_deals} deal{'s' if won_deals != 1 else ''} in the last {days} days. Positive revenue momentum.",
                detail={"won_deals": (won_opps.records or [])[:5], "data_receipt": data_receipt},
                sources=won_opps.sources[:5],
                logic_explanation=f"Queried Salesforce Opportunities where Account.Name matches, IsClosed = true, and CloseDate is within the last {days} days. Filtered for won deals (IsWon = true). Found {won_deals}.",
                actions=[
                    {"label": "View in Salesforce", "action_type": "source_link", "params": {}},
                ],
            ))

        if lost_deals_count > 0:
            insights.append(InsightCard(
                agent_instance_id=ctx.instance_id,
                agent_blueprint_id=self.blueprint.id,
                account_name=account_name,
                priority=Priority.HIGH,
                title=f"{lost_deals_count} deal{'s' if lost_deals_count != 1 else ''} lost recently",
                summary=f"{account_name} lost {lost_deals_count} opportunity(ies) in the last {days} days. Review for pattern or competitive displacement.",
                detail={"lost_deals": (lost_opps.records or [])[:5], "data_receipt": data_receipt},
                sources=lost_opps.sources[:5],
                logic_explanation=f"Queried Salesforce Opportunities where Account.Name matches, IsClosed = true, and CloseDate is within the last {days} days. Filtered for lost deals (IsWon = false). Found {lost_deals_count}.",
                actions=[
                    {"label": "View Pipeline", "action_type": "source_link", "params": {}},
                ],
            ))

        if open_opps.records:
            stalled = [o for o in open_opps.records if not o.get("NextStep")]
            if stalled:
                insights.append(InsightCard(
                    agent_instance_id=ctx.instance_id,
                    agent_blueprint_id=self.blueprint.id,
                    account_name=account_name,
                    priority=Priority.MEDIUM,
                    title=f"{len(stalled)} stalled deal{'s' if len(stalled) != 1 else ''}",
                    summary=f"{account_name} has {len(stalled)} open opportunities with no defined next step.",
                    detail={"stalled_deals": stalled[:5], "data_receipt": data_receipt},
                    sources=open_opps.sources[:5],
                    logic_explanation=f"Queried Salesforce Opportunities where IsClosed = false. Checked each open deal for the 'NextStep' field. Deals with no NextStep value are flagged as stalled. Found {len(stalled)} out of {open_deals} open deals without a next step.",
                    actions=[
                        {"label": "View Pipeline", "action_type": "source_link", "params": {}},
                    ],
                ))

        # --- Engagement gaps ---
        activity_count = len(activities.records) if activities.records else 0
        if activity_count < 2:
            also_found = []
            case_count = len(cases.records) if cases.records else 0
            if case_count:
                also_found.append(f"{case_count} case{'s' if case_count != 1 else ''}")
            if open_deals:
                also_found.append(f"{open_deals} open deal{'s' if open_deals != 1 else ''}")
            if won_deals:
                also_found.append(f"{won_deals} recent win{'s' if won_deals != 1 else ''}")
            also_context = f" Also found: {', '.join(also_found)}." if also_found else " No cases or pipeline data found either."

            insights.append(InsightCard(
                agent_instance_id=ctx.instance_id,
                agent_blueprint_id=self.blueprint.id,
                account_name=account_name,
                priority=Priority.MEDIUM,
                title="Low engagement detected",
                summary=f"{account_name} has {'no' if activity_count == 0 else 'only ' + str(activity_count)} recorded activit{'ies' if activity_count != 1 else 'y'} in the last {days} days. Consider scheduling outreach.{also_context}",
                detail={"activity_count": activity_count, "data_receipt": data_receipt},
                sources=activities.sources,
                logic_explanation=f"Queried Salesforce Tasks/Activities where Account matches and CreatedDate is within the last {days} days (limit 50). Threshold: fewer than 2 activities. Found {activity_count}. Also queried: Cases ({case_count} found), Open Opportunities ({open_deals} found), Closed-Won ({won_deals} found), Closed-Lost ({lost_deals_count} found).",
                actions=[
                    {"label": "Prep Meeting", "action_type": "run_agent",
                     "params": {"agent": "meeting_prep", "account": account_name}},
                ],
            ))

        # --- Stable / all-clear (with evidence of what was checked) ---
        if not insights:
            summary_parts = []
            if cases.records:
                summary_parts.append(f"{len(cases.records)} cases ({case_open_count} open, {case_closed_count} closed)")
            else:
                summary_parts.append("0 cases")
            if open_deals:
                summary_parts.append(f"{open_deals} active deal{'s' if open_deals != 1 else ''}")
            else:
                summary_parts.append("no open pipeline")
            if won_deals:
                summary_parts.append(f"{won_deals} recent win{'s' if won_deals != 1 else ''}")
            if lost_deals_count:
                summary_parts.append(f"{lost_deals_count} recent loss{'es' if lost_deals_count != 1 else ''}")
            summary_parts.append(f"{activity_count} activit{'ies' if activity_count != 1 else 'y'}")

            total_records = (len(cases.records or []) + open_deals + won_deals +
                           lost_deals_count + activity_count)
            if total_records == 0:
                if cases.error or open_opps.error:
                    source_note = "Salesforce returned no data — connector may be down or account name may not match."
                else:
                    source_note = f"No Salesforce records found for this account in the last {days} days."
                summary_text = f"{account_name}: {source_note}"
            else:
                summary_text = f"{account_name} — checked {', '.join(summary_parts)} over the last {days} days. No critical risks, stalled deals, or engagement gaps detected."

            insights.append(InsightCard(
                agent_instance_id=ctx.instance_id,
                agent_blueprint_id=self.blueprint.id,
                account_name=account_name,
                priority=Priority.INFO,
                title="Stable — no action needed",
                summary=summary_text,
                detail={"data_receipt": data_receipt},
                sources=all_sources[:5],
                logic_explanation=f"Ran 5 Salesforce queries (Cases, Open Opps, Closed-Won, Closed-Lost, Activities) for the last {days} days. None of the alert thresholds were triggered: no critical/high cases open, fewer than 5 open cases, no lost deals, no stalled deals (all have NextStep), and 2+ activities logged.",
                actions=[
                    {"label": "Generate Full Brief", "action_type": "generate_briefing",
                     "params": {"account_name": account_name, "type": "internal"}},
                ],
            ))

        return insights
