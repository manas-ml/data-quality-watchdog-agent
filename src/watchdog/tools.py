from __future__ import annotations

import json
from typing import Any

from watchdog.anomaly import compute_anomaly_score as _compute_anomaly_score
from watchdog.baseline.store import BaselineStore
from watchdog.checks.custom_rules import CustomRuleCheck
from watchdog.checks.freshness import FreshnessCheck
from watchdog.checks.null_rate import NullRateCheck
from watchdog.checks.schema_drift import SchemaDriftCheck
from watchdog.checks.volume import VolumeCheck
from watchdog.connectors.base import AbstractConnector
from watchdog.models import ColumnDef, WatchdogConfig

# ---------------------------------------------------------------------------
# Tool schemas (passed to Claude via the `tools` parameter)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "get_table_freshness",
        "description": (
            "Checks how recently a table was updated by querying MAX(timestamp_col). "
            "Returns age in minutes since the most recent row."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string", "description": "Table to check"},
                "timestamp_col": {
                    "type": "string",
                    "description": "Column containing load or event timestamps",
                },
            },
            "required": ["table_name", "timestamp_col"],
        },
    },
    {
        "name": "get_row_count",
        "description": "Returns the current row count for a table.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string", "description": "Table to count"},
            },
            "required": ["table_name"],
        },
    },
    {
        "name": "get_null_rates",
        "description": (
            "Measures the null/missing-value rate (0–100 %) for each specified column."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string"},
                "columns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Columns to inspect for nulls",
                },
            },
            "required": ["table_name", "columns"],
        },
    },
    {
        "name": "get_current_schema",
        "description": (
            "Returns the current column list (name, data_type, is_nullable) for a table. "
            "Also returns the previous schema from the baseline so you can detect drift."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string"},
            },
            "required": ["table_name"],
        },
    },
    {
        "name": "run_custom_rule",
        "description": (
            "Executes a user-supplied SQL statement that returns rows violating a business rule "
            "(duplicates, invalid enums, negative amounts, orphan records). "
            "Returns the violation count and up to 5 sample rows."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string"},
                "rule_name": {"type": "string", "description": "Human-readable rule label"},
                "sql": {
                    "type": "string",
                    "description": "Read-only SELECT that returns violating rows",
                },
                "threshold": {
                    "type": "integer",
                    "description": "Maximum acceptable violations (default 0)",
                    "default": 0,
                },
            },
            "required": ["table_name", "rule_name", "sql"],
        },
    },
    {
        "name": "get_metric_history",
        "description": (
            "Retrieves recent historical measurements for a specific metric from the baseline store. "
            "Use this to get the data needed for anomaly scoring."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string"},
                "metric_name": {
                    "type": "string",
                    "description": "e.g. 'row_count', 'freshness_minutes', or 'null_rate:<col>'",
                },
                "column_name": {
                    "type": "string",
                    "description": "Column name for column-level metrics; omit for table-level",
                },
                "window": {
                    "type": "integer",
                    "description": "Number of historical data points to retrieve (default 30)",
                    "default": 30,
                },
            },
            "required": ["table_name", "metric_name"],
        },
    },
    {
        "name": "compute_anomaly_score",
        "description": (
            "Computes a statistical anomaly score for a single observed value against its history. "
            "Uses z-score when N>=5, otherwise percentage-change fallback. "
            "Returns severity: INFO, WARNING, ALERT, or CRITICAL."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "current": {"type": "number", "description": "The observed value"},
                "history": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Historical values (oldest first)",
                },
                "z_threshold": {
                    "type": "number",
                    "description": "Z-score threshold for anomaly (default 3.0)",
                    "default": 3.0,
                },
            },
            "required": ["current", "history"],
        },
    },
    {
        "name": "record_metric_and_schema",
        "description": (
            "Persists the current run's metrics and schema to the baseline store "
            "so future runs have historical data for comparison."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string"},
                "metrics": {
                    "type": "object",
                    "description": (
                        "Dict of metric_name -> value to record. "
                        "For column-level metrics use 'null_rate:<col>' as the key."
                    ),
                    "additionalProperties": {"type": "number"},
                },
                "schema_columns": {
                    "type": "array",
                    "description": "Current column definitions [{name, data_type, is_nullable}]",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "data_type": {"type": "string"},
                            "is_nullable": {"type": "boolean"},
                        },
                        "required": ["name", "data_type", "is_nullable"],
                    },
                },
            },
            "required": ["table_name", "metrics"],
        },
    },
    {
        "name": "parse_dbt_manifest",
        "description": (
            "Parse a dbt manifest.json file to extract the project structure: models, tests, "
            "compiled SQL, and the lineage child_map. Returns an overview of all nodes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "manifest_path": {"type": "string", "description": "Absolute path to manifest.json"},
            },
            "required": ["manifest_path"],
        },
    },
    {
        "name": "parse_dbt_run_results",
        "description": (
            "Parse a dbt run_results.json file to get test and model execution results. "
            "Returns pass/fail/error counts and per-test details including failure row counts. "
            "Pass manifest_path to enrich results with test type, column, and compiled SQL."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "run_results_path": {"type": "string", "description": "Absolute path to run_results.json"},
                "manifest_path": {
                    "type": "string",
                    "description": "Optional path to manifest.json to enrich results with test metadata",
                },
            },
            "required": ["run_results_path"],
        },
    },
    {
        "name": "get_dbt_test_sql",
        "description": (
            "Retrieve the compiled SQL for a specific dbt test from the manifest. "
            "Use this to understand exactly what a failing test checks, then investigate "
            "the underlying data using run_custom_rule."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "test_unique_id": {
                    "type": "string",
                    "description": "The unique_id of the test (e.g. 'test.jaffle_shop.not_null_orders_customer_id')",
                },
                "manifest_path": {"type": "string", "description": "Absolute path to manifest.json"},
            },
            "required": ["test_unique_id", "manifest_path"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool dispatcher — maps tool names to handler functions
# ---------------------------------------------------------------------------

class ToolDispatcher:
    def __init__(
        self,
        connector: AbstractConnector,
        baseline: BaselineStore,
        config: WatchdogConfig,
    ) -> None:
        self._connector = connector
        self._baseline = baseline
        self._config = config

        self._freshness = FreshnessCheck(connector)
        self._volume = VolumeCheck(connector)
        self._null_rate = NullRateCheck(connector)
        self._schema_drift = SchemaDriftCheck(connector)
        self._custom_rule = CustomRuleCheck(connector)

    def dispatch(self, name: str, inputs: dict[str, Any]) -> Any:
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return {"error": f"Unknown tool: {name}"}
        return handler(**inputs)

    # ---- individual tool handlers ----------------------------------------

    def _tool_get_table_freshness(self, table_name: str, timestamp_col: str) -> dict:
        result = self._freshness.run(table_name, timestamp_col=timestamp_col)
        return result.model_dump()

    def _tool_get_row_count(self, table_name: str) -> dict:
        result = self._volume.run(table_name)
        return result.model_dump()

    def _tool_get_null_rates(self, table_name: str, columns: list[str]) -> dict:
        result = self._null_rate.run(table_name, columns=columns)
        return result.model_dump()

    def _tool_get_current_schema(self, table_name: str) -> dict:
        previous = self._baseline.get_last_schema(table_name)
        result = self._schema_drift.run(table_name, previous=previous)
        return result.model_dump()

    def _tool_run_custom_rule(
        self,
        table_name: str,
        rule_name: str,
        sql: str,
        threshold: int = 0,
    ) -> dict:
        result = self._custom_rule.run(
            table_name, rule_name=rule_name, sql=sql, threshold=threshold
        )
        return result.model_dump()

    def _tool_get_metric_history(
        self,
        table_name: str,
        metric_name: str,
        column_name: str | None = None,
        window: int = 30,
    ) -> dict:
        history = self._baseline.get_history(table_name, metric_name, column_name, window)
        return {"table_name": table_name, "metric_name": metric_name, "history": history}

    def _tool_compute_anomaly_score(
        self,
        current: float,
        history: list[float],
        z_threshold: float = 3.0,
    ) -> dict:
        score = _compute_anomaly_score(current, history, z_threshold)
        return score.model_dump()

    def _tool_record_metric_and_schema(
        self,
        table_name: str,
        metrics: dict[str, float],
        schema_columns: list[dict] | None = None,
    ) -> dict:
        for metric_name, value in metrics.items():
            col = None
            if ":" in metric_name:
                _, col = metric_name.split(":", 1)
            self._baseline.record_metric(table_name, metric_name, value, column_name=col)

        if schema_columns:
            cols = [ColumnDef(**c) for c in schema_columns]
            self._baseline.record_schema(table_name, cols)

        return {"recorded": True, "metrics_count": len(metrics)}

    # ---- dbt artifact tool handlers -----------------------------------------

    def _tool_parse_dbt_manifest(self, manifest_path: str) -> dict:
        from watchdog.dbt.manifest import parse_manifest
        return parse_manifest(manifest_path)

    def _tool_parse_dbt_run_results(
        self,
        run_results_path: str,
        manifest_path: str | None = None,
    ) -> dict:
        from watchdog.dbt.run_results import parse_run_results
        return parse_run_results(run_results_path, manifest_path)

    def _tool_get_dbt_test_sql(self, test_unique_id: str, manifest_path: str) -> dict:
        from watchdog.dbt.manifest import get_test_compiled_sql
        return get_test_compiled_sql(test_unique_id, manifest_path)
