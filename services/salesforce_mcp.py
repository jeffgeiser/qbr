"""
Salesforce MCP Client Service

Manages the lifecycle of the Salesforce MCP server subprocess and provides
methods to query Cases, Opportunities, Contacts, and Activities for QBR briefings.
"""

import os
import json
import logging
from contextlib import AsyncExitStack
from datetime import datetime, timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)


class SalesforceMCPClient:
    """Manages connection to the Salesforce MCP server via stdio transport."""

    def __init__(self):
        self.session: ClientSession | None = None
        self._exit_stack: AsyncExitStack | None = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected and self.session is not None

    async def connect(self):
        """Start the MCP server subprocess and initialize the session."""
        if self._connected:
            return

        self._exit_stack = AsyncExitStack()
        await self._exit_stack.__aenter__()

        server_params = StdioServerParameters(
            command="npx",
            args=["-y", "@tsmztech/mcp-server-salesforce"],
            env={
                "SALESFORCE_CONNECTION_TYPE": os.environ.get(
                    "SALESFORCE_CONNECTION_TYPE", "OAuth_2.0_Client_Credentials"
                ),
                "SALESFORCE_CLIENT_ID": os.environ.get("SALESFORCE_CLIENT_ID", ""),
                "SALESFORCE_CLIENT_SECRET": os.environ.get("SALESFORCE_CLIENT_SECRET", ""),
                "SALESFORCE_INSTANCE_URL": os.environ.get("SALESFORCE_INSTANCE_URL", ""),
                # Also pass PATH so npx can find node
                "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            },
        )

        read, write = await self._exit_stack.enter_async_context(
            stdio_client(server_params)
        )

        self.session = await self._exit_stack.enter_async_context(
            ClientSession(read, write)
        )

        await self.session.initialize()
        self._connected = True

        tools = await self.session.list_tools()
        tool_names = [t.name for t in tools.tools]
        logger.info(f"Salesforce MCP connected. Tools: {tool_names}")

    async def disconnect(self):
        """Shut down the MCP server subprocess."""
        if self._exit_stack:
            await self._exit_stack.aclose()
            self.session = None
            self._connected = False
            logger.info("Salesforce MCP disconnected.")

    async def _call_tool(self, tool_name: str, arguments: dict) -> list[dict]:
        """Call an MCP tool and parse the response."""
        if not self.session:
            raise RuntimeError("Salesforce MCP session not initialized. Call connect() first.")

        result = await self.session.call_tool(tool_name, arguments=arguments)

        if result.isError:
            error_text = result.content[0].text if result.content else "Unknown error"
            raise RuntimeError(f"Salesforce MCP tool '{tool_name}' error: {error_text}")

        parsed = []
        for item in result.content:
            if hasattr(item, "text"):
                try:
                    parsed.append(json.loads(item.text))
                except json.JSONDecodeError:
                    parsed.append({"text": item.text})
            else:
                parsed.append({"value": str(item)})
        return parsed

    async def _query(self, soql: str) -> list[dict]:
        """Execute a SOQL query and return results."""
        return await self._call_tool("salesforce_query_records", {"query": soql})

    # --- QBR-Specific Data Fetching Methods ---

    async def get_account_cases(self, account_name: str, days: int = 90) -> list[dict]:
        """Fetch cases for an account within the given time range."""
        since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        soql = (
            f"SELECT Id, CaseNumber, Subject, Status, Priority, CreatedDate, ClosedDate, "
            f"Description, ContactId, Contact.Name "
            f"FROM Case "
            f"WHERE Account.Name = '{_escape(account_name)}' "
            f"AND CreatedDate >= {since} "
            f"ORDER BY CreatedDate DESC"
        )
        return await self._query(soql)

    async def get_open_opportunities(self, account_name: str) -> list[dict]:
        """Fetch open opportunities for an account."""
        soql = (
            f"SELECT Id, Name, StageName, Amount, CloseDate, Probability, Description, "
            f"Type, NextStep "
            f"FROM Opportunity "
            f"WHERE Account.Name = '{_escape(account_name)}' "
            f"AND IsClosed = false "
            f"ORDER BY Amount DESC"
        )
        return await self._query(soql)

    async def get_closed_opportunities(self, account_name: str, days: int = 90) -> list[dict]:
        """Fetch recently closed (won/lost) opportunities."""
        since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        soql = (
            f"SELECT Id, Name, StageName, Amount, CloseDate, IsWon, Description, Type "
            f"FROM Opportunity "
            f"WHERE Account.Name = '{_escape(account_name)}' "
            f"AND IsClosed = true "
            f"AND CloseDate >= {since[:10]} "
            f"ORDER BY CloseDate DESC"
        )
        return await self._query(soql)

    async def get_contacts(self, account_name: str) -> list[dict]:
        """Fetch contacts for an account."""
        soql = (
            f"SELECT Id, Name, Email, Phone, Title, Department "
            f"FROM Contact "
            f"WHERE Account.Name = '{_escape(account_name)}' "
            f"ORDER BY Name"
        )
        return await self._query(soql)

    async def get_activities(self, account_name: str, days: int = 90) -> list[dict]:
        """Fetch recent tasks/activities for an account."""
        since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        soql = (
            f"SELECT Id, Subject, Status, ActivityDate, Priority, Description "
            f"FROM Task "
            f"WHERE Account.Name = '{_escape(account_name)}' "
            f"AND CreatedDate >= {since} "
            f"ORDER BY ActivityDate DESC "
            f"LIMIT 50"
        )
        return await self._query(soql)

    async def get_account_info(self, account_name: str) -> list[dict]:
        """Fetch the Salesforce account record itself."""
        soql = (
            f"SELECT Id, Name, Type, Industry, AnnualRevenue, NumberOfEmployees, "
            f"Description, OwnerId, Owner.Name "
            f"FROM Account "
            f"WHERE Name = '{_escape(account_name)}' "
            f"LIMIT 1"
        )
        return await self._query(soql)

    async def fetch_all_briefing_data(self, account_name: str, days: int = 90) -> dict:
        """
        Fetch all data needed for briefing generation in one call.
        Returns a dict with keys: account_info, cases, open_opportunities,
        closed_opportunities, contacts, activities.
        """
        import asyncio

        # Run all queries concurrently
        results = await asyncio.gather(
            self.get_account_info(account_name),
            self.get_account_cases(account_name, days),
            self.get_open_opportunities(account_name),
            self.get_closed_opportunities(account_name, days),
            self.get_contacts(account_name),
            self.get_activities(account_name, days),
            return_exceptions=True,
        )

        def safe_result(r):
            if isinstance(r, Exception):
                logger.warning(f"Salesforce query failed: {r}")
                return []
            return r

        return {
            "account_info": safe_result(results[0]),
            "cases": safe_result(results[1]),
            "open_opportunities": safe_result(results[2]),
            "closed_opportunities": safe_result(results[3]),
            "contacts": safe_result(results[4]),
            "activities": safe_result(results[5]),
        }


def _escape(value: str) -> str:
    """Escape single quotes for SOQL injection prevention."""
    return value.replace("'", "\\'")


# Singleton instance
salesforce_client = SalesforceMCPClient()
