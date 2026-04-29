"""
Seed a demo DuckDB warehouse + baseline SQLite so the watchdog has historical
data to work with on the first real run.

Usage:
    python seed_demo.py
    watchdog --table orders --timestamp-col created_at \
             --critical-cols order_id,customer_id,amount \
             --custom-rule "negative_amounts::SELECT * FROM orders WHERE amount < 0::0" \
             --db-path demo.duckdb \
             --baseline-path demo_baseline.db
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import duckdb

from watchdog.baseline.store import BaselineStore
from watchdog.models import ColumnDef

DB_PATH = "demo.duckdb"
BASELINE_PATH = "demo_baseline.db"
HISTORY_DAYS = 30
ROWS_PER_DAY = 500


def seed() -> None:
    print("Seeding demo DuckDB warehouse …")
    con = duckdb.connect(DB_PATH)

    con.execute("DROP TABLE IF EXISTS orders")
    con.execute("""
        CREATE TABLE orders (
            order_id    INTEGER PRIMARY KEY,
            customer_id INTEGER,
            amount      DOUBLE,
            status      VARCHAR,
            created_at  TIMESTAMP
        )
    """)

    rows = []
    order_id = 1
    statuses = ["pending", "processing", "shipped", "delivered", "cancelled"]
    now = datetime.now(timezone.utc)

    for day in range(HISTORY_DAYS, 0, -1):
        ts = now - timedelta(days=day)
        count = ROWS_PER_DAY
        # Inject a volume spike on day 15
        if day == 15:
            count = int(ROWS_PER_DAY * 3.5)
        for _ in range(count):
            rows.append(
                (
                    order_id,
                    random.randint(1, 1000),
                    round(random.uniform(5, 500), 2),
                    random.choice(statuses),
                    ts.strftime("%Y-%m-%d %H:%M:%S"),
                )
            )
            order_id += 1

    # Today's rows — add some anomalies
    for _ in range(50):  # Unusually low count (normally 500)
        rows.append(
            (
                order_id,
                None if random.random() < 0.2 else random.randint(1, 1000),  # 20% null customer_id
                -abs(round(random.uniform(5, 100), 2)) if random.random() < 0.1 else round(random.uniform(5, 500), 2),
                random.choice(statuses),
                now.strftime("%Y-%m-%d %H:%M:%S"),
            )
        )
        order_id += 1

    con.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?)", rows)
    print(f"  Inserted {len(rows):,} orders across {HISTORY_DAYS} days + today")

    print("Seeding baseline history …")
    store = BaselineStore(BASELINE_PATH)

    # Back-fill row_count history (simulates 30 previous runs)
    for day in range(HISTORY_DAYS, 0, -1):
        ts = now - timedelta(days=day)
        count = ROWS_PER_DAY
        if day == 15:
            count = int(ROWS_PER_DAY * 3.5)
        store.record_metric("orders", "row_count", float(count), measured_at=ts)

    # Back-fill freshness history
    for day in range(HISTORY_DAYS, 0, -1):
        ts = now - timedelta(days=day)
        store.record_metric("orders", "freshness_minutes", 5.0, measured_at=ts)

    # Back-fill null_rate history
    for day in range(HISTORY_DAYS, 0, -1):
        ts = now - timedelta(days=day)
        store.record_metric("orders", "null_rate:customer_id", 0.2, measured_at=ts)
        store.record_metric("orders", "null_rate:amount", 0.0, measured_at=ts)

    # Record current schema snapshot
    schema_cols = [
        ColumnDef(name="order_id", data_type="INTEGER", is_nullable=False),
        ColumnDef(name="customer_id", data_type="INTEGER", is_nullable=True),
        ColumnDef(name="amount", data_type="DOUBLE", is_nullable=True),
        ColumnDef(name="status", data_type="VARCHAR", is_nullable=True),
        ColumnDef(name="created_at", data_type="TIMESTAMP", is_nullable=True),
    ]
    store.record_schema("orders", schema_cols)

    print(f"  Baseline written to {BASELINE_PATH}")
    print()
    print("Demo ready. Run:")
    print(
        f'  watchdog --table orders --timestamp-col created_at '
        f'--critical-cols order_id,customer_id,amount '
        f'--custom-rule "negative_amounts::SELECT * FROM orders WHERE amount < 0::0" '
        f'--db-path {DB_PATH} --baseline-path {BASELINE_PATH}'
    )


if __name__ == "__main__":
    seed()
