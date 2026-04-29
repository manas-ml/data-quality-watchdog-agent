from __future__ import annotations

from abc import ABC, abstractmethod

from watchdog.connectors.base import AbstractConnector
from watchdog.models import CheckResult


class BaseCheck(ABC):
    def __init__(self, connector: AbstractConnector) -> None:
        self.connector = connector

    @abstractmethod
    def run(self, table_name: str, **kwargs) -> CheckResult:
        """Execute the check and return a result."""
