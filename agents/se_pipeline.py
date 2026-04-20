"""
SE Pipeline Tracker — Active POCs, pipeline by SE, and recent closes.

Designed for SE leadership. Queries Salesforce Opportunities for:
- Active POCs (any opp with POC Status populated and not closed)
- Pipeline by SE (deals forecast to close in next 90 days)
- Recently closed-won deals grouped by SE

Sends a formatted summary to Teams every Monday (or on-demand).
"""

import os
import json
import logging
from datetime import datetime, timedelta
from collections import defaultdict

from core.agent_runtime import BaseAgent, AgentBlueprint
from core.models import AgentContext, AgentResult, InsightCard, Priority, SourceObject

logger = logging.getLogger(__name__)


class SEPipelineAgent(BaseAgent):

    blueprint = AgentBlueprint(
        id="se_pipeline",
        name="SE Pipeline Tracker",
        description="Tracks active POCs, pipeline by SE, and recent closes. Sends a weekly summary to your Teams channel and runs on-demand.",
        category="intelligence",
        icon="beaker",
        color="cyan",
        required_integrations=["salesforce"],
        default_config={
            "teams_webhook_url": "",
            "poc_status_field": "POC_Status__c",
            "se_field": "Solution_Engineer__c",
            "mrr_field": "Opportunity_Total_MRR__c",
            "forecast_days": 90,
            "recent_close_days": 30,
        },
        capabilities=["poc_tracking", "se_pipeline", "weekly_digest"],
        schedule_options=["manual", "daily", "weekly"],
        data_sources=[
            "Salesforce Opportunities — POC Status field (active POCs)",
            "Salesforce Opportunities — Solution Engineer, Total MRR, CloseDate (pipeline by SE)",
            "Salesforce Opportunities — recently closed-won grouped by SE",
        ],
        logic_steps=[
            "Queries open opps where POC Status is populated → active POCs",
            "Queries open opps closing within forecast window → pipeline by SE",
            "Queries closed-won opps in recent period → wins by SE",
            "Groups all results by Solution Engineer",
            "Formats summary with opp details: account, MRR, stage, SE, close date",
            "Pushes formatted card to Teams webhook if configured",
        ],
        output_types=["Active POC list", "Pipeline by SE", "Recent wins by SE", "Teams notification"],
    )

    async def run(self, context: AgentContext) -> AgentResult:
        insights: list[InsightCard] = []
        errors: list[str] = []
        config = context.config

        poc_field = config.get("poc_status_field", "POC_Status__c")
        se_field = config.get("se_field", "Solution_Engineer__c")
        mrr_field = config.get("mrr_field", "Opportunity_Total_MRR__c")
        forecast_days = config.get("forecast_days", 90)
        recent_days = config.get("recent_close_days", 30)

        try:
            from services.salesforce_mcp import salesforce_client as client
            if not client.is_connected:
                return AgentResult(success=False, errors=["Salesforce not connected"])

            # Base fields that always exist — custom fields added separately
            base_fields = [
                "Id", "Name", "StageName", "Amount", "CloseDate", "Probability",
                "Type", "NextStep", "IsClosed", "IsWon",
                "Account.Name", "Owner.Name",
            ]
            custom_fields = [poc_field, se_field, mrr_field]
            opp_fields = base_fields + custom_fields

            # 1. Active POCs
            poc_records: list[dict] = []
            try:
                poc_raw = await client._query(
                    "Opportunity", opp_fields,
                    where=f"{poc_field} != null AND IsClosed = false",
                    order_by=f"{se_field}, Account.Name",
                )
                poc_records = client._parse_text_records(poc_raw)
            except Exception as e:
                err_str = str(e)
                if "No such column" in err_str or "invalid field" in err_str.lower():
                    errors.append(
                        f"Custom field '{poc_field}' not found in Salesforce. "
                        f"Update poc_status_field in Config to the correct API name. (Error: {err_str})"
                    )
                else:
                    errors.append(f"POC query failed: {err_str}")
                logger.warning(f"SE Pipeline POC query failed: {e}")

            # 2. Pipeline closing in forecast window
            forecast_date = (datetime.utcnow() + timedelta(days=forecast_days)).strftime("%Y-%m-%d")
            pipeline_records: list[dict] = []
            try:
                pipeline_raw = await client._query(
                    "Opportunity", opp_fields,
                    where=f"IsClosed = false AND CloseDate <= {forecast_date}",
                    order_by=f"{se_field}, CloseDate",
                )
                pipeline_records = client._parse_text_records(pipeline_raw)
            except Exception as e:
                err_str = str(e)
                if "No such column" in err_str or "invalid field" in err_str.lower():
                    # Retry without custom fields so we at least get pipeline data
                    try:
                        pipeline_raw = await client._query(
                            "Opportunity", base_fields,
                            where=f"IsClosed = false AND CloseDate <= {forecast_date}",
                            order_by="CloseDate",
                        )
                        pipeline_records = client._parse_text_records(pipeline_raw)
                        errors.append(
                            f"Custom fields ({se_field}, {mrr_field}) not found — showing pipeline without SE/MRR grouping. "
                            f"Update field names in Config."
                        )
                    except Exception as e2:
                        errors.append(f"Pipeline query failed: {e2}")
                else:
                    errors.append(f"Pipeline query failed: {err_str}")
                logger.warning(f"SE Pipeline pipeline query failed: {e}")

            # 3. Recently closed-won
            since = (datetime.utcnow() - timedelta(days=recent_days)).strftime("%Y-%m-%d")
            won_records: list[dict] = []
            try:
                won_raw = await client._query(
                    "Opportunity", opp_fields,
                    where=f"IsClosed = true AND IsWon = true AND CloseDate >= {since}",
                    order_by=f"{se_field}, CloseDate DESC",
                )
                won_records = client._parse_text_records(won_raw)
            except Exception as e:
                logger.warning(f"SE Pipeline won query failed: {e}")
                errors.append(f"Won deals query failed: {e}")

        except Exception as e:
            logger.error(f"SE Pipeline setup failed: {e}", exc_info=True)
            return AgentResult(success=False, errors=[f"Salesforce error: {e}"])

        sf_url = os.environ.get("SALESFORCE_INSTANCE_URL", "").rstrip("/")

        # --- Active POCs card ---
        if poc_records:
            poc_by_se = self._group_by_field(poc_records, se_field)
            poc_lines = []
            for se, opps in poc_by_se.items():
                poc_lines.append(f"**{se or 'Unassigned'}** ({len(opps)} POC{'s' if len(opps) != 1 else ''})")
                for o in opps[:8]:
                    mrr = o.get(mrr_field, o.get("Amount", "N/A"))
                    poc_status = o.get(poc_field, "")
                    poc_lines.append(f"  • {o.get('Account.Name', o.get('Name', '?'))} — MRR: {mrr} — Status: {poc_status}")

            insights.append(InsightCard(
                agent_instance_id=context.instance_id,
                agent_blueprint_id=self.blueprint.id,
                account_name="All Accounts",
                priority=Priority.MEDIUM,
                title=f"{len(poc_records)} active POC{'s' if len(poc_records) != 1 else ''}",
                summary=f"{len(poc_records)} opportunities in active POC across {len(poc_by_se)} SE{'s' if len(poc_by_se) != 1 else ''}.",
                detail={"poc_by_se": {k: v[:10] for k, v in poc_by_se.items()}, "total": len(poc_records)},
                logic_explanation=f"Queried Salesforce Opportunities where {poc_field} is not null AND IsClosed = false. Found {len(poc_records)} active POCs grouped by {se_field}.",
                actions=[],
            ))
        else:
            insights.append(InsightCard(
                agent_instance_id=context.instance_id,
                agent_blueprint_id=self.blueprint.id,
                account_name="All Accounts",
                priority=Priority.INFO,
                title="No active POCs",
                summary=f"No opportunities found with a POC Status set. Field checked: {poc_field}.",
                detail={},
                logic_explanation=f"Queried Salesforce Opportunities where {poc_field} != null AND IsClosed = false. Returned 0 records. If this seems wrong, verify the API field name matches your Salesforce setup.",
                actions=[],
            ))

        # --- Pipeline by SE card ---
        if pipeline_records:
            pipe_by_se = self._group_by_field(pipeline_records, se_field)
            pipe_summary_parts = []
            for se, opps in pipe_by_se.items():
                total_mrr = sum(self._parse_number(o.get(mrr_field, o.get("Amount", 0))) for o in opps)
                pipe_summary_parts.append(f"{se or 'Unassigned'}: {len(opps)} deals, ${total_mrr:,.0f} MRR")

            insights.append(InsightCard(
                agent_instance_id=context.instance_id,
                agent_blueprint_id=self.blueprint.id,
                account_name="All Accounts",
                priority=Priority.INFO,
                title=f"Pipeline closing next {forecast_days} days: {len(pipeline_records)} deal{'s' if len(pipeline_records) != 1 else ''}",
                summary="; ".join(pipe_summary_parts),
                detail={"pipeline_by_se": {k: v[:10] for k, v in pipe_by_se.items()}, "total": len(pipeline_records)},
                logic_explanation=f"Queried Salesforce Opportunities where IsClosed = false AND CloseDate <= {forecast_date}. Found {len(pipeline_records)} deals grouped by {se_field}. MRR from {mrr_field} field.",
                actions=[],
            ))

        # --- Recent wins by SE card ---
        if won_records:
            won_by_se = self._group_by_field(won_records, se_field)
            won_summary_parts = []
            for se, opps in won_by_se.items():
                total_mrr = sum(self._parse_number(o.get(mrr_field, o.get("Amount", 0))) for o in opps)
                won_summary_parts.append(f"{se or 'Unassigned'}: {len(opps)} won, ${total_mrr:,.0f} MRR")

            insights.append(InsightCard(
                agent_instance_id=context.instance_id,
                agent_blueprint_id=self.blueprint.id,
                account_name="All Accounts",
                priority=Priority.INFO,
                title=f"{len(won_records)} deal{'s' if len(won_records) != 1 else ''} closed-won in last {recent_days} days",
                summary="; ".join(won_summary_parts),
                detail={"won_by_se": {k: v[:10] for k, v in won_by_se.items()}, "total": len(won_records)},
                logic_explanation=f"Queried Salesforce Opportunities where IsClosed = true, IsWon = true, CloseDate >= {since}. Found {len(won_records)} grouped by {se_field}.",
                actions=[],
            ))

        # --- Push to Teams ---
        webhook_url = config.get("teams_webhook_url", "")
        if webhook_url:
            await self._push_to_teams(webhook_url, poc_records, pipeline_records,
                                       won_records, se_field, mrr_field, poc_field,
                                       forecast_days, recent_days, sf_url)

        return AgentResult(success=True, insights=insights, errors=errors)

    def _group_by_field(self, records: list[dict], field: str) -> dict[str, list[dict]]:
        grouped: dict[str, list[dict]] = defaultdict(list)
        for r in records:
            key = r.get(field, r.get("Solution_Engineer__c", "Unassigned")) or "Unassigned"
            grouped[key].append(r)
        return dict(grouped)

    @staticmethod
    def _parse_number(val) -> float:
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str):
            cleaned = val.replace("$", "").replace(",", "").strip()
            try:
                return float(cleaned)
            except (ValueError, TypeError):
                return 0.0
        return 0.0

    async def _push_to_teams(self, webhook_url, pocs, pipeline, won,
                              se_field, mrr_field, poc_field,
                              forecast_days, recent_days, sf_url):
        try:
            from integrations.teams_webhook import send_teams_message

            sections = []

            # POC section
            if pocs:
                poc_by_se = self._group_by_field(pocs, se_field)
                lines = []
                for se, opps in poc_by_se.items():
                    lines.append(f"**{se or 'Unassigned'}**")
                    for o in opps[:6]:
                        mrr = o.get(mrr_field, o.get("Amount", "N/A"))
                        acct = o.get("Account.Name", o.get("Name", "?"))
                        status = o.get(poc_field, "")
                        opp_id = o.get("Id", "")
                        link = f"[{acct}]({sf_url}/{opp_id})" if sf_url and opp_id else acct
                        lines.append(f"  • {link} — MRR: {mrr} — POC: {status}")
                sections.append({
                    "activityTitle": f"Active POCs ({len(pocs)})",
                    "text": "\n\n".join(lines),
                    "markdown": True,
                })

            # Pipeline section
            if pipeline:
                pipe_by_se = self._group_by_field(pipeline, se_field)
                lines = []
                for se, opps in pipe_by_se.items():
                    total = sum(self._parse_number(o.get(mrr_field, o.get("Amount", 0))) for o in opps)
                    lines.append(f"**{se or 'Unassigned'}** — {len(opps)} deals, ${total:,.0f} MRR")
                    for o in opps[:4]:
                        mrr = o.get(mrr_field, o.get("Amount", "N/A"))
                        acct = o.get("Account.Name", o.get("Name", "?"))
                        close = o.get("CloseDate", "?")
                        opp_id = o.get("Id", "")
                        link = f"[{acct}]({sf_url}/{opp_id})" if sf_url and opp_id else acct
                        lines.append(f"  • {link} — MRR: {mrr} — Close: {close}")
                sections.append({
                    "activityTitle": f"Pipeline Next {forecast_days} Days ({len(pipeline)} deals)",
                    "text": "\n\n".join(lines),
                    "markdown": True,
                })

            # Won section
            if won:
                won_by_se = self._group_by_field(won, se_field)
                lines = []
                for se, opps in won_by_se.items():
                    total = sum(self._parse_number(o.get(mrr_field, o.get("Amount", 0))) for o in opps)
                    lines.append(f"**{se or 'Unassigned'}** — {len(opps)} won, ${total:,.0f} MRR")
                    for o in opps[:4]:
                        mrr = o.get(mrr_field, o.get("Amount", "N/A"))
                        acct = o.get("Account.Name", o.get("Name", "?"))
                        opp_id = o.get("Id", "")
                        link = f"[{acct}]({sf_url}/{opp_id})" if sf_url and opp_id else acct
                        lines.append(f"  • {link} — MRR: {mrr}")
                sections.append({
                    "activityTitle": f"Recently Closed-Won ({len(won)} deals, last {recent_days}d)",
                    "text": "\n\n".join(lines),
                    "markdown": True,
                })

            if not sections:
                sections = [{"text": "No POCs, pipeline, or recent wins found."}]

            await send_teams_message(
                webhook_url,
                "SE Pipeline Report",
                f"{len(pocs)} POCs, {len(pipeline)} pipeline, {len(won)} won",
                sections,
                theme_color="06B6D4",
            )
        except Exception as e:
            logger.error(f"SE Pipeline Teams push failed: {e}")
