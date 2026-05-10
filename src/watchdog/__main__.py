from __future__ import annotations

import argparse
import sys

from watchdog.agent import run_watchdog
from watchdog.models import CustomRule, WatchdogConfig
from watchdog.responder import emit_report


def _parse_custom_rule(raw: str) -> CustomRule:
    """Parse 'name::sql::threshold' string into a CustomRule."""
    parts = raw.split("::", 2)
    if len(parts) < 2:
        raise argparse.ArgumentTypeError(
            "Custom rule must be 'name::sql' or 'name::sql::threshold'"
        )
    name = parts[0]
    sql = parts[1]
    threshold = int(parts[2]) if len(parts) == 3 else 0
    return CustomRule(name=name, sql=sql, threshold=threshold)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="watchdog",
        description="Data Quality Watchdog Agent — powered by Claude",
    )
    parser.add_argument("--table", required=True, help="Table name to audit")
    parser.add_argument("--timestamp-col", default=None, help="Timestamp column for freshness check")
    parser.add_argument(
        "--critical-cols",
        default="",
        help="Comma-separated column names to check for null rates",
    )
    parser.add_argument(
        "--custom-rule",
        action="append",
        default=[],
        dest="custom_rules",
        metavar="name::sql[::threshold]",
        help="Custom SQL rule (repeatable)",
    )
    parser.add_argument("--db-path", default=":memory:", help="DuckDB database path")
    parser.add_argument("--baseline-path", default="baseline.db", help="SQLite baseline path")
    parser.add_argument("--z-threshold", type=float, default=3.0, help="Z-score anomaly threshold")
    parser.add_argument("--history-window", type=int, default=30, help="Historical window size")
    parser.add_argument("--manifest-path", default=None, help="Path to dbt manifest.json")
    parser.add_argument("--run-results-path", default=None, help="Path to dbt run_results.json")

    args = parser.parse_args()

    critical_cols = [c.strip() for c in args.critical_cols.split(",") if c.strip()]
    custom_rules = [_parse_custom_rule(r) for r in args.custom_rules]

    config = WatchdogConfig(
        table_name=args.table,
        timestamp_col=args.timestamp_col,
        critical_cols=critical_cols,
        custom_rules=custom_rules,
        db_path=args.db_path,
        baseline_path=args.baseline_path,
        anomaly_z_threshold=args.z_threshold,
        history_window=args.history_window,
        manifest_path=args.manifest_path,
        run_results_path=args.run_results_path,
    )

    report = run_watchdog(config)
    emit_report(report)

    # Exit with non-zero code when severity is ALERT or CRITICAL
    sev = report.get("overall_severity", "INFO")
    if sev in ("ALERT", "CRITICAL"):
        sys.exit(1)


if __name__ == "__main__":
    main()
