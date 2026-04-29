# Data Quality Watchdog Agent

An always-on data quality analyst for your warehouse, powered by the [Claude Agent SDK](https://docs.anthropic.com/en/docs/agents). It measures core quality signals, detects anomalies against historical baselines, explains likely root causes, and emits a severity-graded report to stdout.

## What it monitors

| Check | What it catches |
|---|---|
| **Freshness** | Stale tables — time since last load or max event timestamp |
| **Volume** | Row count spikes and drops vs. a rolling baseline |
| **Null rate** | Missing values on keys, timestamps, and required fields |
| **Schema drift** | Added, removed, or type-changed columns |
| **Custom rules** | Duplicate business keys, invalid enums, negative amounts, orphan records |

## How it works

The agent uses Claude's tool-use loop. On each run, Claude is given a system prompt and a table configuration, then calls eight Python tools to gather metrics, retrieve historical baselines, compute anomaly scores, and persist state. After all checks complete, Claude synthesises findings and emits a structured JSON report explaining likely root causes and recommended actions.

```
CLI → WatchdogConfig → Claude (claude-sonnet-4-6)
                           │
              ┌────────────┼────────────────────┐
              ▼            ▼                    ▼
       get_row_count  get_null_rates    get_current_schema
       get_table_freshness              run_custom_rule
              │
       get_metric_history ──► compute_anomaly_score
              │
       record_metric_and_schema ──► SQLite baseline
              │
         end_turn → JSON report → stdout
```

**Anomaly detection:** z-score (primary, when ≥ 5 history points) with percentage-change fallback for new tables. Severity thresholds:

| Severity | Z-score | Pct change |
|---|---|---|
| INFO | \|z\| < 2 | < 10 % |
| WARNING | 2 – 3 | 10 – 30 % |
| ALERT | 3 – 5 | 30 – 70 % |
| CRITICAL | > 5 | > 70 % |

## Installation

```bash
git clone <repo>
cd data-quality-watchdog-agent
pip install -e .
```

Set your API key:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

## Quick start

**1. Seed a demo warehouse** (creates `demo.duckdb` + 30 days of baseline history):

```bash
python seed_demo.py
```

**2. Run a check:**

```bash
watchdog \
  --table orders \
  --timestamp-col created_at \
  --critical-cols order_id,customer_id,amount \
  --custom-rule "negative_amounts::SELECT * FROM orders WHERE amount < 0::0" \
  --db-path demo.duckdb \
  --baseline-path demo_baseline.db
```

**Sample output:**

```
╔════════════════════════════════════════════════════════════╗
║ DATA QUALITY REPORT                                        ║
╠════════════════════════════════════════════════════════════╣
║ Table    : orders                                          ║
║ Severity : ▲ ALERT                                         ║
║ Time     : 2026-04-29T14:32:00Z                            ║
╠════════════════════════════════════════════════════════════╣
║ FINDINGS                                                   ║
╠════════════════════════════════════════════════════════════╣
║ [ALERT]    ▲ Volume anomaly: 50 rows (z=-4.1, expected ~500)║
║ [WARNING]  ! Null rate on customer_id: 20.0% (baseline 0.2%)║
║ [ALERT]    ▲ Custom rule 'negative_amounts': 5 violations  ║
║ [INFO]     ✓ Freshness: 2 minutes                          ║
║ [INFO]     ✓ Schema: no drift detected                     ║
╠════════════════════════════════════════════════════════════╣
║ ROOT CAUSE                                                 ║
╠════════════════════════════════════════════════════════════╣
║ Today's load appears partial — row count is 90% below      ║
║ the 30-day mean. The elevated null rate on customer_id      ║
║ and negative amounts suggest the upstream ETL job failed    ║
║ mid-run and wrote malformed records.                        ║
╠════════════════════════════════════════════════════════════╣
║ RECOMMENDED ACTION                                         ║
╠════════════════════════════════════════════════════════════╣
║ Investigate the ETL job logs for today's run. Re-load      ║
║ after fixing the upstream issue. Consider quarantining      ║
║ the 5 negative-amount records.                             ║
╚════════════════════════════════════════════════════════════╝
```

Exit code is `1` when severity is ALERT or CRITICAL, making it CI-friendly.

## CLI reference

```
watchdog [OPTIONS]

Options:
  --table TEXT                Table to audit (required)
  --timestamp-col TEXT        Column to use for freshness check
  --critical-cols TEXT        Comma-separated columns to check for null rates
  --custom-rule TEXT          Rule in format: name::sql[::threshold]
                              (repeatable, threshold defaults to 0)
  --db-path TEXT              DuckDB file path (default: :memory:)
  --baseline-path TEXT        SQLite baseline path (default: baseline.db)
  --z-threshold FLOAT         Z-score anomaly threshold (default: 3.0)
  --history-window INT        Historical data points to use (default: 30)
```

### Custom rule format

Custom rules are SQL `SELECT` statements that return violating rows. The threshold is the maximum acceptable violation count (default `0`).

```bash
# Duplicate order IDs
--custom-rule "dup_keys::SELECT order_id, COUNT(*) FROM orders GROUP BY order_id HAVING COUNT(*) > 1::0"

# Invalid status values
--custom-rule "bad_status::SELECT * FROM orders WHERE status NOT IN ('pending','shipped','delivered')::0"

# Orphan order items
--custom-rule "orphans::SELECT i.* FROM order_items i LEFT JOIN orders o ON i.order_id = o.id WHERE o.id IS NULL::0"
```

## Project structure

```
src/watchdog/
├── __main__.py          CLI entry point
├── agent.py             Claude tool-use agent loop
├── tools.py             8 tool schemas + dispatcher
├── models.py            Pydantic v2 models
├── anomaly.py           Z-score / pct-change anomaly detection
├── responder.py         Stdout report formatter
├── baseline/
│   └── store.py         SQLite baseline store
├── connectors/
│   ├── base.py          AbstractConnector
│   └── duckdb_connector.py
└── checks/
    ├── base.py
    ├── freshness.py
    ├── volume.py
    ├── null_rate.py
    ├── schema_drift.py
    └── custom_rules.py
tests/
├── conftest.py          In-memory DuckDB + SQLite fixtures
├── test_checks.py       Unit tests for all five checks
├── test_baseline.py     Baseline store CRUD + history tests
└── test_agent.py        Agent loop tests (mocked Claude API)
seed_demo.py             Demo warehouse + 30-day baseline seeder
```

## Running tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## Extending

**Add a new check:** create a class in `src/watchdog/checks/` that extends `BaseCheck`, implement `run()` returning a `CheckResult`, then expose it as a tool in `tools.py` with a schema entry in `TOOL_SCHEMAS` and a handler method prefixed `_tool_` in `ToolDispatcher`.

**Connect to a real warehouse:** swap `--db-path` for any SQLAlchemy-compatible URL. The `DuckDBConnector` speaks plain SQL; a `PostgreSQLConnector` following the same `AbstractConnector` interface would drop in without changes to the checks or agent.
