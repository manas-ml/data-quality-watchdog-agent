from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from watchdog.models import ColumnDef

_DDL = """
CREATE TABLE IF NOT EXISTS metric_snapshots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name   TEXT    NOT NULL,
    metric_name  TEXT    NOT NULL,
    column_name  TEXT,
    value        REAL    NOT NULL,
    measured_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_metric_lookup
    ON metric_snapshots (table_name, metric_name, column_name);

CREATE TABLE IF NOT EXISTS schema_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name  TEXT    NOT NULL,
    columns_json TEXT   NOT NULL,
    captured_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_schema_lookup
    ON schema_snapshots (table_name, captured_at);
"""


class BaselineStore:
    def __init__(self, db_path: str) -> None:
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(db_path, check_same_thread=False)
        self._con.executescript(_DDL)
        self._con.commit()

    def record_metric(
        self,
        table_name: str,
        metric_name: str,
        value: float,
        column_name: str | None = None,
        measured_at: datetime | None = None,
    ) -> None:
        ts = (measured_at or datetime.now(timezone.utc)).isoformat()
        self._con.execute(
            "INSERT INTO metric_snapshots (table_name, metric_name, column_name, value, measured_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (table_name, metric_name, column_name, value, ts),
        )
        self._con.commit()

    def get_history(
        self,
        table_name: str,
        metric_name: str,
        column_name: str | None = None,
        window: int = 30,
    ) -> list[float]:
        rows = self._con.execute(
            "SELECT value FROM metric_snapshots"
            " WHERE table_name = ? AND metric_name = ? AND column_name IS ?"
            " ORDER BY measured_at DESC LIMIT ?",
            (table_name, metric_name, column_name, window),
        ).fetchall()
        return [r[0] for r in reversed(rows)]

    def record_schema(self, table_name: str, columns: list[ColumnDef]) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        payload = json.dumps([c.model_dump() for c in columns])
        self._con.execute(
            "INSERT INTO schema_snapshots (table_name, columns_json, captured_at) VALUES (?, ?, ?)",
            (table_name, payload, ts),
        )
        self._con.commit()

    def get_last_schema(self, table_name: str) -> list[ColumnDef] | None:
        row = self._con.execute(
            "SELECT columns_json FROM schema_snapshots WHERE table_name = ?"
            " ORDER BY captured_at DESC LIMIT 1",
            (table_name,),
        ).fetchone()
        if row is None:
            return None
        return [ColumnDef(**c) for c in json.loads(row[0])]
