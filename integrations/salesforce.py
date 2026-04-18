"""
Salesforce MCP Connector - wraps the existing SalesforceMCPClient
into the IntegrationConnector interface with SourceObject support.
"""

import os
import json
import logging
from datetime import datetime

from integrations.base import IntegrationConnector
from core.models import ConnectorResult, SourceObject

logger = logging.getLogger(__name__)


class SalesforceMCPConnector(IntegrationConnector):

    name = "salesforce"
    capabilities = [
        "cases", "opportunities", "contacts", "activities", "account_info",
        "support_tickets", "pipeline", "deals", "customer_interactions",
    ]

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            from services.salesforce_mcp import salesforce_client
            self._client = salesforce_client
        return self._client

    def _instance_url(self) -> str:
        return os.environ.get("SALESFORCE_INSTANCE_URL", "").rstrip("/")

    def _make_source(self, object_type: str, record: dict, display: str) -> SourceObject:
        obj_id = record.get("Id", "")
        base_url = self._instance_url()
        deep_link = f"{base_url}/{obj_id}" if base_url and obj_id else ""
        return SourceObject(
            source_type="salesforce",
            object_type=object_type,
            object_id=obj_id,
            display_name=display,
            deep_link=deep_link,
            snippet=record.get("Subject", record.get("Name", "")),
            retrieved_at=datetime.utcnow().isoformat(),
        )

    async def query(self, intent: str, params: dict) -> ConnectorResult:
        client = self._get_client()
        account_name = params.get("account_name", "")
        days = params.get("days", 90)
        sources: list[SourceObject] = []

        try:
            if not client.is_connected:
                return ConnectorResult(
                    connector_name=self.name, intent=intent,
                    error="Salesforce not connected",
                )

            # Check for mapped Salesforce Account IDs first
            sf_ids = params.get("salesforce_ids") or []
            if not sf_ids:
                try:
                    from main import get_salesforce_ids_for_account
                    sf_ids = get_salesforce_ids_for_account(account_name)
                except Exception:
                    pass

            if sf_ids:
                af = self._build_id_filter(sf_ids)
                logger.info(f"[SF] Using mapped Account IDs for '{account_name}': {sf_ids}")
            else:
                account_name = await client.resolve_account_name(account_name)
                af = ""

            if intent in ("cases", "support_tickets"):
                raw = await client.get_account_cases(account_name, days, account_filter=af)
                records = client._parse_text_records(raw)
                for r in records:
                    sources.append(self._make_source("Case", r, r.get("CaseNumber", "Case")))

            elif intent in ("opportunities", "pipeline", "deals"):
                status = params.get("status", "all")
                if status == "open":
                    raw = await client.get_open_opportunities(account_name, account_filter=af)
                elif status in ("won", "lost"):
                    raw = await client.get_closed_opportunities(account_name, days, account_filter=af)
                else:
                    open_ops = await client.get_open_opportunities(account_name, account_filter=af)
                    closed_ops = await client.get_closed_opportunities(account_name, days, account_filter=af)
                    raw = open_ops + closed_ops
                records = client._parse_text_records(raw)
                for r in records:
                    sources.append(self._make_source("Opportunity", r, r.get("Name", "Opportunity")))

            elif intent == "contacts":
                raw = await client.get_contacts(account_name, account_filter=af)
                records = client._parse_text_records(raw)
                for r in records:
                    sources.append(self._make_source("Contact", r, r.get("Name", "Contact")))

            elif intent in ("activities", "customer_interactions"):
                raw = await client.get_activities(account_name, days, account_filter=af)
                records = client._parse_text_records(raw)
                for r in records:
                    sources.append(self._make_source("Task", r, r.get("Subject", "Activity")))

            elif intent == "account_info":
                raw = await client.get_account_info(account_name, account_filter=af)
                records = client._parse_text_records(raw)
                for r in records:
                    sources.append(self._make_source("Account", r, r.get("Name", account_name)))

            elif intent == "all":
                data = await client.fetch_all_briefing_data(account_name, days)
                records = []
                for key, raw_list in data.items():
                    parsed = client._parse_text_records(raw_list) if isinstance(raw_list, list) else []
                    obj_type = key.replace("_", " ").title()
                    for r in parsed:
                        sources.append(self._make_source(obj_type, r,
                                                         r.get("Name", r.get("CaseNumber", obj_type))))
                    records.extend(parsed)
            else:
                return ConnectorResult(connector_name=self.name, intent=intent,
                                       error=f"Unknown intent: {intent}")

            return ConnectorResult(
                connector_name=self.name, intent=intent,
                records=records, sources=sources,
                record_count=len(records),
                raw_text=json.dumps(raw if intent != "all" else data, default=str),
            )

        except Exception as e:
            logger.error(f"Salesforce connector error: {e}", exc_info=True)
            return ConnectorResult(connector_name=self.name, intent=intent, error=str(e))

    @staticmethod
    def _build_id_filter(sf_ids: list[str]) -> str:
        escaped = [sid.replace("'", "\\'") for sid in sf_ids if sid]
        if len(escaped) == 1:
            return f"AccountId = '{escaped[0]}'"
        id_list = "','".join(escaped)
        return f"AccountId IN ('{id_list}')"

    @staticmethod
    def _escape_soql(value: str) -> str:
        return value.replace("'", "\\'")

    async def health_check(self) -> bool:
        return self._get_client().is_connected

    async def connect(self):
        await self._get_client().connect()

    async def disconnect(self):
        await self._get_client().disconnect()
