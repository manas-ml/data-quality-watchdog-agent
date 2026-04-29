from __future__ import annotations

import pytest
import duckdb

from watchdog.baseline.store import BaselineStore
from watchdog.connectors.duckdb_connector import DuckDBConnector


@pytest.fixture(scope="session")
def duckdb_con():
    """In-memory DuckDB connection shared across the test session."""
    con = duckdb.connect(":memory:")
    con.execute("""
        CREATE TABLE orders (
            order_id    INTEGER,
            customer_id INTEGER,
            amount      DOUBLE,
            status      VARCHAR,
            created_at  TIMESTAMP
        )
    """)
    con.execute("""
        INSERT INTO orders VALUES
            (1, 10, 99.99,  'shipped',   '2026-04-28 10:00:00'),
            (2, 11, 149.00, 'pending',   '2026-04-28 11:00:00'),
            (3, 12, NULL,   'cancelled', '2026-04-28 12:00:00'),
            (4, NULL, 25.0, 'pending',   '2026-04-28 13:00:00'),
            (5, 14, -10.0,  'shipped',   '2026-04-28 14:00:00')
    """)
    return con


@pytest.fixture
def connector(duckdb_con):
    """DuckDB connector wrapping the shared in-memory connection."""
    c = DuckDBConnector.__new__(DuckDBConnector)
    c._con = duckdb_con
    return c


@pytest.fixture
def baseline(tmp_path):
    """Fresh baseline store backed by a temp SQLite file."""
    return BaselineStore(str(tmp_path / "baseline.db"))
