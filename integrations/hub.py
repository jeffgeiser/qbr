"""
Integration Hub - routes semantic data queries to the right connector(s).

Agents request data by intent ("cases", "pipeline", "contacts"); the hub
finds the connector that can fulfill the request.
"""

import logging
from typing import Optional
from integrations.base import IntegrationConnector
from core.models import ConnectorResult

logger = logging.getLogger(__name__)


class IntegrationHub:

    def __init__(self):
        self._connectors: dict[str, IntegrationConnector] = {}
        self._capability_map: dict[str, list[str]] = {}

    def register(self, connector: IntegrationConnector):
        self._connectors[connector.name] = connector
        for cap in connector.capabilities:
            self._capability_map.setdefault(cap, []).append(connector.name)
        logger.info(f"Registered connector: {connector.name} ({connector.capabilities})")

    def get_connector(self, name: str) -> Optional[IntegrationConnector]:
        return self._connectors.get(name)

    async def query(self, intent: str, params: dict, connector_name: str = "") -> ConnectorResult:
        if connector_name:
            connector = self._connectors.get(connector_name)
            if not connector:
                return ConnectorResult(connector_name=connector_name, intent=intent,
                                       error=f"Connector '{connector_name}' not found")
            return await connector.query(intent, params)

        for cap, names in self._capability_map.items():
            if cap == intent or intent in cap:
                connector = self._connectors[names[0]]
                return await connector.query(intent, params)

        return ConnectorResult(connector_name="none", intent=intent,
                               error=f"No connector for intent: {intent}")

    async def health_check_all(self) -> dict[str, bool]:
        statuses = {}
        for name, connector in self._connectors.items():
            try:
                statuses[name] = await connector.health_check()
            except Exception:
                statuses[name] = False
        return statuses

    def get_all_statuses(self) -> list[dict]:
        return [
            {"name": c.name, "capabilities": c.capabilities,
             "connected": getattr(c, '_client', None) is not None}
            for c in self._connectors.values()
        ]


hub = IntegrationHub()
