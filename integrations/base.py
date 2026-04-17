"""
Integration Connector base class.

All data source connectors (Salesforce, Confluence, M365, OSS APIs)
implement this interface so agents query data by semantic intent
rather than connector-specific APIs.
"""

from abc import ABC, abstractmethod
from core.models import ConnectorResult


class IntegrationConnector(ABC):

    name: str = ""
    capabilities: list[str] = []

    @abstractmethod
    async def query(self, intent: str, params: dict) -> ConnectorResult:
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        pass

    @abstractmethod
    async def connect(self):
        pass

    @abstractmethod
    async def disconnect(self):
        pass
