from __future__ import annotations

import json

import anthropic

from watchdog.baseline.store import BaselineStore
from watchdog.connectors.duckdb_connector import DuckDBConnector
from watchdog.models import WatchdogConfig
from watchdog.tools import TOOL_SCHEMAS, ToolDispatcher

MAX_TURNS = 20
MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """\
You are a Data Quality Watchdog Agent — an always-on analyst for a data warehouse.

Your job is to thoroughly audit the given table and produce a complete quality report.

## Workflow

For the table you are asked to inspect, follow these steps in order:

0. **dbt artifacts** (only when manifest_path and run_results_path are provided) —
   Run this step BEFORE the warehouse checks below:
   a. Call `parse_dbt_manifest` with the manifest_path to understand models, tests, and lineage.
   b. Call `parse_dbt_run_results` with the run_results_path AND manifest_path to get
      a full pass/fail summary of the last dbt run.
   c. For every test with status "fail" or "error":
      - Call `get_dbt_test_sql` to retrieve its compiled SQL and metadata.
      - Call `run_custom_rule` using that compiled SQL and the test's attached model as
        table_name to confirm violations and retrieve sample failing rows.
      - Look up the model in the manifest child_map to list all downstream models
        that are affected (blast radius).
   d. Severity mapping for dbt findings:
      - status="error" (compile/runtime failure) → CRITICAL
      - status="fail" on a unique or not_null test on a key column → CRITICAL
      - status="fail" on other tests → ALERT
      - All tests pass → INFO

1. **Row count** — Call `get_row_count`. Then call `get_metric_history` for metric
   `row_count` and `compute_anomaly_score` to detect volume anomalies.

2. **Freshness** — If a timestamp column is specified, call `get_table_freshness`.
   Then call `get_metric_history` for metric `freshness_minutes` and
   `compute_anomaly_score`.

3. **Null rates** — If critical columns are specified, call `get_null_rates`.
   For each column call `get_metric_history` for metric `null_rate:<col>` and
   `compute_anomaly_score`.

4. **Schema drift** — Call `get_current_schema`. If columns were added or removed,
   treat removed columns as CRITICAL and added columns as WARNING.

5. **Custom rules** — For each custom rule specified, call `run_custom_rule`.

6. **Persist state** — Call `record_metric_and_schema` once with all collected
   metrics and the current schema, so future runs have baseline data.

7. **Final assessment** — Output a JSON object (and nothing else) with this shape:

```json
{
  "table": "<name>",
  "overall_severity": "INFO|WARNING|ALERT|CRITICAL",
  "findings": [
    {
      "check": "<check name>",
      "severity": "INFO|WARNING|ALERT|CRITICAL",
      "message": "<one-line human description>",
      "detail": {}
    }
  ],
  "dbt_summary": {
    "total_tests": 0,
    "passed": 0,
    "failed": 0,
    "errored": 0,
    "failing_tests": []
  },
  "root_cause": "<Claude's reasoning about likely causes>",
  "recommended_action": "<what the operator should do>"
}
```

The `dbt_summary` field should only be included when dbt artifacts were provided.
Each entry in `failing_tests` should include the test name, type, column, failure count,
and a list of affected downstream models.

## Severity rules
- INFO: all checks pass, no anomalies.
- WARNING: minor anomaly (z-score 2–3 or pct change 10–30 %).
- ALERT: significant anomaly (z-score 3–5 or pct change 30–70 %, or custom rule violations, or dbt test failures).
- CRITICAL: severe anomaly (z-score >5, pct change >70 %, missing column, total data loss, or dbt test errors).

Overall severity = maximum severity across all findings.

Be precise and concise. Do not skip any configured check.
"""


def _build_user_prompt(config: WatchdogConfig) -> str:
    lines = [f"Audit table: **{config.table_name}**"]
    if config.manifest_path:
        lines.append(f"dbt manifest: {config.manifest_path}")
    if config.run_results_path:
        lines.append(f"dbt run results: {config.run_results_path}")
    if config.timestamp_col:
        lines.append(f"Timestamp column: {config.timestamp_col}")
    if config.critical_cols:
        lines.append(f"Critical columns (check null rates): {', '.join(config.critical_cols)}")
    if config.custom_rules:
        lines.append("Custom rules to enforce:")
        for rule in config.custom_rules:
            lines.append(f"  - {rule.name}: {rule.sql} (threshold={rule.threshold})")
    lines.append(f"Anomaly z-score threshold: {config.anomaly_z_threshold}")
    lines.append(f"History window: {config.history_window} data points")
    return "\n".join(lines)


def run_watchdog(config: WatchdogConfig) -> dict:
    """Run the Claude agent loop and return the final report dict."""
    connector = DuckDBConnector(config.db_path)
    baseline = BaselineStore(config.baseline_path)
    dispatcher = ToolDispatcher(connector, baseline, config)

    client = anthropic.Anthropic()
    messages: list[dict] = [
        {"role": "user", "content": _build_user_prompt(config)}
    ]

    for _ in range(MAX_TURNS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )

        # Accumulate assistant message (content is a list of blocks)
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            # Extract the JSON text block from the final response
            for block in response.content:
                if hasattr(block, "text"):
                    text = block.text.strip()
                    # Strip markdown code fences if present
                    if text.startswith("```"):
                        text = text.split("```")[1]
                        if text.startswith("json"):
                            text = text[4:]
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        return {"raw": text, "parse_error": True}
            return {"error": "No text block in final response"}

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = dispatcher.dispatch(block.name, block.input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, default=str),
                        }
                    )
            messages.append({"role": "user", "content": tool_results})

    return {"error": "Max turns reached without a final response"}
