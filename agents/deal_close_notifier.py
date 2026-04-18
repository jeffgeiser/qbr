"""
Deal Close Notifier — Pushes closed-won deals to a leadership Teams channel.

Runs daily. Scans for deals that closed in the last 24 hours (configurable).
For each closed deal, pushes: opp link, Total MRR, account name, SE,
rep (owner), and contacts on the opportunity.
"""

import os
import json
import logging
from datetime import datetime, timedelta

from core.agent_runtime import BaseAgent, AgentBlueprint
from core.models import AgentContext, AgentResult, InsightCard, Priority, SourceObject

logger = logging.getLogger(__name__)


class DealCloseNotifierAgent(BaseAgent):

    blueprint = AgentBlueprint(
        id="deal_close_notifier",
        name="Deal Close Notifier",
        description="Pushes closed-won deals to your leadership Teams channel. Runs daily — surfaces new wins with opp link, MRR, account, rep, SE, and contacts.",
        category="intelligence",
        icon="trophy",
        color="gold",
        required_integrations=["salesforce"],
        default_config={
            "teams_webhook_url": "",
            "lookback_hours": 24,
            "se_field": "Solution_Engineer__c",
            "mrr_field": "Opportunity_Total_MRR__c",
        },
        capabilities=["deal_notifications", "win_alerts", "leadership_updates"],
        schedule_options=["manual", "daily"],
        data_sources=[
            "Salesforce Opportunities — closed-won in lookback window",
            "Salesforce Contacts — contacts associated with the winning account",
        ],
        logic_steps=[
            "Queries closed-won opportunities where CloseDate is within lookback window (default 24h)",
            "For each won deal, fetches account contacts from Salesforce",
            "Builds notification with opp link, MRR, account, owner (rep), SE, contacts",
            "Pushes each deal as a card to the configured Teams webhook",
            "Also creates insight cards in the workbench feed",
        ],
        output_types=["Win notification per deal", "Teams channel alert"],
    )

    async def run(self, context: AgentContext) -> AgentResult:
        insights: list[InsightCard] = []
        errors: list[str] = []
        config = context.config

        se_field = config.get("se_field", "Solution_Engineer__c")
        mrr_field = config.get("mrr_field", "Opportunity_Total_MRR__c")
        lookback_hours = config.get("lookback_hours", 24)
        webhook_url = config.get("teams_webhook_url", "")

        try:
            from services.salesforce_mcp import salesforce_client as client
            if not client.is_connected:
                return AgentResult(success=False, errors=["Salesforce not connected"])

            since = (datetime.utcnow() - timedelta(hours=lookback_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
            since_date = (datetime.utcnow() - timedelta(hours=lookback_hours)).strftime("%Y-%m-%d")

            opp_fields = [
                "Id", "Name", "StageName", "Amount", "CloseDate",
                "Type", "Account.Name", "Account.Id", "Owner.Name",
                se_field, mrr_field,
            ]

            won_raw = await client._query(
                "Opportunity", opp_fields,
                where=f"IsClosed = true AND IsWon = true AND CloseDate >= {since_date}",
                order_by="CloseDate DESC",
            )
            won_records = client._parse_text_records(won_raw)

        except Exception as e:
            logger.error(f"Deal Close Notifier query failed: {e}", exc_info=True)
            return AgentResult(success=False, errors=[f"Salesforce query failed: {e}"])

        if not won_records:
            insights.append(InsightCard(
                agent_instance_id=context.instance_id,
                agent_blueprint_id=self.blueprint.id,
                account_name="All Accounts",
                priority=Priority.INFO,
                title=f"No new wins in the last {lookback_hours} hours",
                summary="No closed-won opportunities found in the lookback window.",
                detail={},
                logic_explanation=f"Queried Salesforce Opportunities where IsClosed = true, IsWon = true, CloseDate >= {since_date}. Found 0 records.",
                actions=[],
            ))
            return AgentResult(success=True, insights=insights, errors=errors)

        sf_url = os.environ.get("SALESFORCE_INSTANCE_URL", "").rstrip("/")

        for opp in won_records:
            opp_id = opp.get("Id", "")
            opp_name = opp.get("Name", "Unknown Deal")
            account_name = opp.get("Account.Name", "Unknown Account")
            account_id = opp.get("Account.Id", "")
            owner = opp.get("Owner.Name", "Unknown")
            se = opp.get(se_field, "Unassigned")
            mrr = opp.get(mrr_field, opp.get("Amount", "N/A"))
            close_date = opp.get("CloseDate", "")
            opp_link = f"{sf_url}/{opp_id}" if sf_url and opp_id else ""

            # Fetch contacts for this account
            contacts = []
            try:
                from services.salesforce_mcp import salesforce_client as client
                if account_name and account_name != "Unknown Account":
                    contact_raw = await client._query(
                        "Contact",
                        ["Id", "Name", "Email", "Title", "Phone"],
                        where=f"Account.Name = '{account_name.replace(chr(39), chr(92)+chr(39))}'",
                        limit=5,
                    )
                    contacts = client._parse_text_records(contact_raw)
            except Exception as e:
                logger.warning(f"Could not fetch contacts for {account_name}: {e}")

            contact_summary = ""
            if contacts:
                contact_lines = [f"{c.get('Name', '?')} ({c.get('Title', '')})" for c in contacts[:5]]
                contact_summary = "Contacts: " + ", ".join(contact_lines)

            insights.append(InsightCard(
                agent_instance_id=context.instance_id,
                agent_blueprint_id=self.blueprint.id,
                account_name=account_name,
                priority=Priority.INFO,
                title=f"Deal Won: {opp_name}",
                summary=f"{account_name} — MRR: {mrr} — Rep: {owner} — SE: {se} — Closed: {close_date}. {contact_summary}",
                detail={
                    "opportunity": opp,
                    "contacts": contacts[:5],
                    "opp_link": opp_link,
                },
                sources=[SourceObject(
                    source_type="salesforce", object_type="Opportunity",
                    object_id=opp_id, display_name=opp_name,
                    deep_link=opp_link, snippet=f"MRR: {mrr}",
                    retrieved_at=datetime.utcnow().isoformat(),
                )] if opp_id else [],
                logic_explanation=f"Salesforce Opportunity '{opp_name}' has IsClosed = true, IsWon = true, CloseDate = {close_date} (within last {lookback_hours}h). MRR from {mrr_field} field. Contacts fetched from the associated Account.",
                actions=[
                    {"label": "View in Salesforce", "action_type": "external_link",
                     "params": {"url": opp_link}} if opp_link else
                    {"label": "View Details", "action_type": "expand", "params": {}},
                ],
            ))

            # Push to Teams
            if webhook_url:
                await self._push_deal_to_teams(
                    webhook_url, opp_name, account_name, mrr, owner, se,
                    close_date, opp_link, contacts, sf_url,
                )

        return AgentResult(success=True, insights=insights, errors=errors)

    async def _push_deal_to_teams(self, webhook_url, opp_name, account, mrr,
                                   owner, se, close_date, opp_link, contacts, sf_url):
        try:
            from integrations.teams_webhook import send_teams_message

            facts = [
                {"name": "Account", "value": account},
                {"name": "MRR", "value": str(mrr)},
                {"name": "Rep", "value": owner},
                {"name": "Solution Engineer", "value": se or "Unassigned"},
                {"name": "Close Date", "value": close_date},
            ]

            sections = [
                {
                    "activityTitle": opp_name,
                    "activitySubtitle": f"[View in Salesforce]({opp_link})" if opp_link else "",
                    "facts": facts,
                    "markdown": True,
                },
            ]

            if contacts:
                contact_lines = [
                    f"**{c.get('Name', '?')}** — {c.get('Title', 'No title')} — {c.get('Email', '')}"
                    for c in contacts[:5]
                ]
                sections.append({
                    "activityTitle": "Key Contacts",
                    "text": "\n\n".join(contact_lines),
                    "markdown": True,
                })

            await send_teams_message(
                webhook_url,
                f"Deal Won: {account}",
                f"{account} — MRR: {mrr}",
                sections,
                theme_color="10B981",
            )
        except Exception as e:
            logger.error(f"Deal close Teams push failed: {e}")
