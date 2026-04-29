from __future__ import annotations

import duckdb

from watchdog.connectors.base import AbstractConnector
from watchdog.models import ColumnDef


class DuckDBConnector(AbstractConnector):
    def __init__(self, db_path: str = ":memory:") -> None:
        self._con = duckdb.connect(db_path)

    def execute_scalar(self, sql: str) -> float | str | None:
        result = self._con.execute(sql).fetchone()
        if result is None:
            return None
        return result[0]

    def execute_rows(self, sql: str, limit: int = 5) -> list[dict]:
        rel = self._con.execute(sql)
        cols = [d[0] for d in rel.description]
        return [dict(zip(cols, row)) for row in rel.fetchmany(limit)]

    def get_schema(self, table_name: str) -> list[ColumnDef]:
        rows = self._con.execute(f"DESCRIBE {table_name}").fetchall()
        return [
            ColumnDef(
                name=row[0],
                data_type=row[1],
                is_nullable=(row[2].upper() == "YES" if row[2] else True),
            )
            for row in rows
        ]
