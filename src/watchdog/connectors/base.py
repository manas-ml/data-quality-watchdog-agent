from __future__ import annotations

from abc import ABC, abstractmethod

from watchdog.models import ColumnDef


class AbstractConnector(ABC):
    @abstractmethod
    def execute_scalar(self, sql: str) -> float | str | None:
        """Run a query that returns a single value."""

    @abstractmethod
    def execute_rows(self, sql: str, limit: int = 5) -> list[dict]:
        """Run a query and return rows as dicts."""

    @abstractmethod
    def get_schema(self, table_name: str) -> list[ColumnDef]:
        """Return column definitions for a table."""
