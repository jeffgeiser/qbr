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

    async def _query(self, object_name: str, fields: list[str],
                     where: str = "", order_by: str = "", limit: int = 0) -> list[dict]:
        """Execute a structured query via the MCP salesforce_query_records tool."""
        args = {
            "objectName": object_name,
            "fields": fields,
        }
        if where:
            args["whereClause"] = where
        if order_by:
            args["orderBy"] = order_by
        if limit:
            args["limit"] = limit

        logger.info(f"[SF] Query {object_name} where={where}")
        result = await self._call_tool("salesforce_query_records", args)
        logger.info(f"[SF] -> {len(result)} records returned")
        return result

    # --- Account Name Resolution ---

    @staticmethod
    def _parse_text_records(results: list[dict]) -> list[dict]:
        """Parse the MCP text response format into structured records.
        MCP returns: {"text": "Query returned N records:\\n\\nRecord 1:\\n    Name: Foo\\n    Field: Bar\\n\\nRecord 2:\\n..."}
        """
        import re
        records = []
        for r in results:
            if not isinstance(r, dict):
                continue
            # If it's already structured (has keys other than "text"), use it directly
            if "text" not in r or len(r) > 1:
                records.append(r)
                continue
            # Parse the text format
            text = r.get("text", "")
            # Split on "Record N:" boundaries
            record_blocks = re.split(r'Record \d+:', text)
            for block in record_blocks[1:]:  # skip the header "Query returned N records"
                record = {}
                for line in block.strip().split('\n'):
                    line = line.strip()
                    if ':' in line:
                        key, _, value = line.partition(':')
                        record[key.strip()] = value.strip()
                if record:
                    records.append(record)
        return records

    async def resolve_account_name(self, account_name: str) -> str:
        """Resolve a short/partial account name to the exact Salesforce account name.
        Tries exact match first, then LIKE match. Returns the best match."""
        # Try exact match first
        raw = await self._query(
            "Account", ["Name"],
            where=f"Name = '{_escape(account_name)}'",
            limit=1,
        )
        records = self._parse_text_records(raw)
        if records and "Name" in records[0]:
            name = records[0]["Name"]
            logger.info(f"[SF] Exact match for '{account_name}': {name}")
            return name

        # Fall back to LIKE search — pick the best match
        raw = await self._query(
            "Account", ["Name"],
            where=f"Name LIKE '%{_escape(account_name)}%'",
            limit=10,
        )
        records = self._parse_text_records(raw)
        if records:
            names = [r["Name"] for r in records if "Name" in r]
            logger.info(f"[SF] LIKE matches for '{account_name}': {names}")
            # Prefer names that start with the search term
            for n in names:
                if n.lower().startswith(account_name.lower()):
                    logger.info(f"[SF] Best match for '{account_name}': {n}")
                    return n
            # Otherwise return the first match
            logger.info(f"[SF] Using first match for '{account_name}': {names[0]}")
            return names[0]

        logger.warning(f"[SF] No account found matching '{account_name}'")
        return account_name

    # --- QBR-Specific Data Fetching Methods ---
    # Each method accepts an optional account_filter parameter. When provided,
    # it replaces the default Account.Name WHERE clause, enabling ID-based queries.

    def _acct_where(self, account_name: str, account_filter: str = "") -> str:
        """Build the account WHERE clause. Uses account_filter if provided, else Account.Name."""
        if account_filter:
            return account_filter
        return f"Account.Name = '{_escape(account_name)}'"

    async def get_account_cases(self, account_name: str, days: int = 90, account_filter: str = "") -> list[dict]:
        since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        return await self._query(
            "Case",
            ["Id", "CaseNumber", "Subject", "Status", "Priority",
             "CreatedDate", "ClosedDate", "Description", "ContactId", "Contact.Name"],
            where=f"{self._acct_where(account_name, account_filter)} AND CreatedDate >= {since}",
            order_by="CreatedDate DESC",
        )

    async def get_open_opportunities(self, account_name: str, account_filter: str = "") -> list[dict]:
        return await self._query(
            "Opportunity",
            ["Id", "Name", "StageName", "Amount", "CloseDate", "Probability",
             "Description", "Type", "NextStep"],
            where=f"{self._acct_where(account_name, account_filter)} AND IsClosed = false",
            order_by="Amount DESC",
        )

    async def get_closed_opportunities(self, account_name: str, days: int = 90, account_filter: str = "") -> list[dict]:
        since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        return await self._query(
            "Opportunity",
            ["Id", "Name", "StageName", "Amount", "CloseDate", "IsWon",
             "Description", "Type"],
            where=f"{self._acct_where(account_name, account_filter)} AND IsClosed = true AND CloseDate >= {since[:10]}",
            order_by="CloseDate DESC",
        )

    async def get_contacts(self, account_name: str, account_filter: str = "") -> list[dict]:
        return await self._query(
            "Contact",
            ["Id", "Name", "Email", "Phone", "Title", "Department"],
            where=f"{self._acct_where(account_name, account_filter)}",
            order_by="Name",
        )

    async def get_activities(self, account_name: str, days: int = 90, account_filter: str = "") -> list[dict]:
        since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        return await self._query(
            "Task",
            ["Id", "Subject", "Status", "ActivityDate", "Priority", "Description"],
            where=f"{self._acct_where(account_name, account_filter)} AND CreatedDate >= {since}",
            order_by="ActivityDate DESC",
            limit=50,
        )

    async def get_account_info(self, account_name: str, account_filter: str = "") -> list[dict]:
        af = account_filter
        if af:
            af = af.replace("AccountId", "Id")
        else:
            af = f"Name = '{_escape(account_name)}'"
        return await self._query(
            "Account",
            ["Id", "Name", "Type", "Industry", "AnnualRevenue", "NumberOfEmployees",
             "Description", "OwnerId", "Owner.Name"],
            where=af,
            limit=1,
        )

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
