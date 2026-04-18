"""
Account Pulse Agent - Case-centric health monitoring.

Primary signal: Salesforce Cases (volume, severity, open/closed ratio,
subject patterns). Secondary: Pipeline (wins, losses, stalled deals).
Activity data is noted but not weighted heavily since it depends on
reps logging interactions in Salesforce.
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
        description="Case-centric account health monitoring. Analyzes support cases, pipeline movement, and deal status to assess account sentiment.",
        category="intelligence",
        icon="pulse",
        color="emerald",
        required_integrations=["salesforce"],
        default_config={
            "critical_case_threshold": 1,
            "high_volume_threshold": 5,
            "open_ratio_warning": 0.5,
        },
        capabilities=["health_monitoring", "risk_detection", "trend_analysis"],
        schedule_options=["manual", "hourly", "daily", "weekly"],
        data_sources=[
            "Salesforce Cases — primary signal (subject, status, priority, dates)",
            "Salesforce Open Opportunities (stage, amount, next step)",
            "Salesforce Closed-Won Opportunities (recent wins)",
            "Salesforce Closed-Lost Opportunities (recent losses)",
            "Salesforce Activities/Tasks (noted but low-weight — depends on rep logging)",
        ],
        logic_steps=[
            "Computes case health: open/closed ratio, critical case count, subject themes",
            "Derives account sentiment from case patterns (healthy/caution/concern)",
            "Surfaces recent closed-won deals as positive momentum",
            "Flags recently lost deals for competitive review",
            "Identifies stalled deals (open with no defined next step)",
            "Produces an overall health summary card with case details",
            "Boosts priority for accounts marked as must-win",
        ],
        output_types=["Account health summary", "Risk alerts", "Momentum signals"],
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
                       (won_opps.sources or []) + (lost_opps.sources or []))

        # --- Compute case metrics ---
        case_total = len(cases.records) if cases.records else 0
        open_cases = [c for c in (cases.records or []) if c.get("Status", "").lower() not in ("closed", "resolved")]
        closed_cases = [c for c in (cases.records or []) if c.get("Status", "").lower() in ("closed", "resolved")]
        critical_open = [c for c in open_cases if c.get("Priority", "").lower() in ("critical", "high")]
        case_open_count = len(open_cases)
        case_closed_count = len(closed_cases)
        open_ratio = case_open_count / case_total if case_total > 0 else 0
        case_subjects = [c.get("Subject", "") for c in (cases.records or [])[:10] if c.get("Subject")]

        # --- Compute pipeline metrics ---
        open_deals = len(open_opps.records) if open_opps.records else 0
        won_deals = len(won_opps.records) if won_opps.records else 0
        lost_deals_count = len(lost_opps.records) if lost_opps.records else 0
        stalled_deals = [o for o in (open_opps.records or []) if not o.get("NextStep")]
        activity_count = len(activities.records) if activities.records else 0

        data_receipt = {
            "sources_checked": [
                "Salesforce Cases (primary)", "Salesforce Open Opportunities",
                "Salesforce Closed-Won", "Salesforce Closed-Lost",
                "Salesforce Activities (low-weight)",
            ],
            "cases_total": case_total, "cases_open": case_open_count,
            "cases_closed": case_closed_count, "cases_critical_open": len(critical_open),
            "open_ratio": round(open_ratio, 2),
            "open_opportunities": open_deals, "closed_won": won_deals,
            "closed_lost": lost_deals_count, "stalled_deals": len(stalled_deals),
            "activities": activity_count,
            "salesforce_connected": not bool(cases.error),
            "time_range_days": days,
        }

        # --- Determine account sentiment from cases ---
        sentiment = "healthy"
        sentiment_reasons = []

        if len(critical_open) >= ctx.config.get("critical_case_threshold", 1):
            sentiment = "concern"
            sentiment_reasons.append(f"{len(critical_open)} critical/high priority case{'s' if len(critical_open) != 1 else ''} open")

        if case_open_count > ctx.config.get("high_volume_threshold", 5):
            if sentiment != "concern":
                sentiment = "caution"
            sentiment_reasons.append(f"{case_open_count} cases still open (high volume)")

        if open_ratio > ctx.config.get("open_ratio_warning", 0.5) and case_total > 3:
            if sentiment != "concern":
                sentiment = "caution"
            sentiment_reasons.append(f"{int(open_ratio * 100)}% of cases unresolved")

        if lost_deals_count > 0:
            if sentiment == "healthy":
                sentiment = "caution"
            sentiment_reasons.append(f"{lost_deals_count} deal{'s' if lost_deals_count != 1 else ''} lost recently")

        if won_deals > 0:
            sentiment_reasons.append(f"{won_deals} deal{'s' if won_deals != 1 else ''} won (positive)")

        if not sentiment_reasons and case_total == 0 and open_deals == 0:
            sentiment_reasons.append("No case or pipeline data found in Salesforce")

        # --- Build subject preview ---
        subject_preview = ""
        if case_subjects:
            preview_items = case_subjects[:4]
            subject_preview = "; ".join(preview_items)
            if len(case_subjects) > 4:
                subject_preview += f" (+{len(case_subjects) - 4} more)"

        # --- Primary card: Account Health Summary ---
        sentiment_priority = {
            "concern": Priority.HIGH,
            "caution": Priority.MEDIUM,
            "healthy": Priority.INFO,
        }

        summary_parts = []
        if case_total > 0:
            summary_parts.append(f"{case_total} cases ({case_open_count} open, {case_closed_count} closed)")
            if subject_preview:
                summary_parts.append(f"Topics: {subject_preview}")
        else:
            summary_parts.append("No support cases in this period")

        if open_deals:
            summary_parts.append(f"{open_deals} active pipeline deal{'s' if open_deals != 1 else ''}")
        if won_deals:
            summary_parts.append(f"{won_deals} closed-won")
        if lost_deals_count:
            summary_parts.append(f"{lost_deals_count} closed-lost")
        if len(stalled_deals) > 0:
            summary_parts.append(f"{len(stalled_deals)} deal{'s' if len(stalled_deals) != 1 else ''} stalled (no next step)")

        title_sentiment = {"concern": "Needs attention", "caution": "Monitor", "healthy": "Healthy"}

        insights.append(InsightCard(
            agent_instance_id=ctx.instance_id,
            agent_blueprint_id=self.blueprint.id,
            account_name=account_name,
            priority=sentiment_priority[sentiment],
            title=f"{title_sentiment[sentiment]} — {account_name}",
            summary=". ".join(summary_parts) + ".",
            detail={
                "sentiment": sentiment,
                "sentiment_reasons": sentiment_reasons,
                "case_subjects": case_subjects,
                "critical_cases": [{"CaseNumber": c.get("CaseNumber", ""), "Subject": c.get("Subject", ""), "Priority": c.get("Priority", ""), "Status": c.get("Status", "")} for c in critical_open[:5]],
                "stalled_deals": [{"Name": o.get("Name", ""), "StageName": o.get("StageName", ""), "Amount": o.get("Amount", "")} for o in stalled_deals[:5]],
                "data_receipt": data_receipt,
            },
            sources=all_sources[:8],
            logic_explanation=self._build_logic_explanation(sentiment, data_receipt, days, ctx.config),
            actions=[
                {"label": "Generate Full Brief", "action_type": "generate_briefing",
                 "params": {"account_name": account_name, "type": "internal"}},
                {"label": "Meeting Prep", "action_type": "run_agent",
                 "params": {"agent": "meeting_prep", "account": account_name}},
            ],
        ))

        # --- Secondary cards for specific critical alerts ---
        if len(critical_open) > 0:
            crit_subjects = [f"{c.get('CaseNumber', '?')}: {c.get('Subject', 'No subject')}" for c in critical_open[:5]]
            insights.append(InsightCard(
                agent_instance_id=ctx.instance_id,
                agent_blueprint_id=self.blueprint.id,
                account_name=account_name,
                priority=Priority.HIGH,
                title=f"{len(critical_open)} critical case{'s' if len(critical_open) != 1 else ''} requiring action",
                summary="; ".join(crit_subjects),
                detail={"critical_cases": critical_open[:5], "data_receipt": data_receipt},
                sources=cases.sources[:5],
                logic_explanation=f"Salesforce Cases with Priority = 'Critical' or 'High' AND Status not 'Closed'/'Resolved'. Found {len(critical_open)} in the last {days} days.",
                actions=[
                    {"label": "View in Salesforce", "action_type": "source_link", "params": {}},
                ],
            ))

        if lost_deals_count > 0:
            lost_names = [o.get("Name", "Unknown") for o in (lost_opps.records or [])[:5]]
            insights.append(InsightCard(
                agent_instance_id=ctx.instance_id,
                agent_blueprint_id=self.blueprint.id,
                account_name=account_name,
                priority=Priority.HIGH,
                title=f"{lost_deals_count} deal{'s' if lost_deals_count != 1 else ''} lost",
                summary=f"Lost: {'; '.join(lost_names)}. Review for competitive displacement or relationship issues.",
                detail={"lost_deals": (lost_opps.records or [])[:5], "data_receipt": data_receipt},
                sources=lost_opps.sources[:5],
                logic_explanation=f"Salesforce Opportunities where IsClosed = true, IsWon = false, CloseDate within last {days} days. Found {lost_deals_count}.",
                actions=[
                    {"label": "View Pipeline", "action_type": "source_link", "params": {}},
                ],
            ))

        if won_deals > 0:
            won_names = [o.get("Name", "Unknown") for o in (won_opps.records or [])[:5]]
            insights.append(InsightCard(
                agent_instance_id=ctx.instance_id,
                agent_blueprint_id=self.blueprint.id,
                account_name=account_name,
                priority=Priority.INFO,
                title=f"{won_deals} deal{'s' if won_deals != 1 else ''} closed-won",
                summary=f"Won: {'; '.join(won_names)}. Positive revenue momentum.",
                detail={"won_deals": (won_opps.records or [])[:5], "data_receipt": data_receipt},
                sources=won_opps.sources[:5],
                logic_explanation=f"Salesforce Opportunities where IsClosed = true, IsWon = true, CloseDate within last {days} days. Found {won_deals}.",
                actions=[],
            ))

        return insights

    def _build_logic_explanation(self, sentiment: str, receipt: dict, days: int, config: dict) -> str:
        parts = [
            f"Assessed account health over the last {days} days using Salesforce data.",
            f"Cases (primary signal): {receipt['cases_total']} total, {receipt['cases_open']} open, {receipt['cases_closed']} closed, {receipt['cases_critical_open']} critical/high open.",
        ]
        if receipt["cases_total"] > 0:
            parts.append(f"Open ratio: {receipt['open_ratio']:.0%} (warning threshold: {config.get('open_ratio_warning', 0.5):.0%}).")
        parts.append(
            f"Pipeline: {receipt['open_opportunities']} open deals, {receipt['closed_won']} won, {receipt['closed_lost']} lost, {receipt['stalled_deals']} stalled."
        )
        parts.append(
            f"Activities: {receipt['activities']} found (low-weight signal — depends on rep logging in SF)."
        )
        sentiment_labels = {"concern": "Concern (action needed)", "caution": "Caution (monitor)", "healthy": "Healthy"}
        parts.append(f"Derived sentiment: {sentiment_labels.get(sentiment, sentiment)}.")
        return " ".join(parts)
