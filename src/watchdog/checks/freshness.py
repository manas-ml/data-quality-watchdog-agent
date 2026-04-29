from __future__ import annotations

from datetime import datetime, timezone

from watchdog.checks.base import BaseCheck
from watchdog.models import CheckResult


class FreshnessCheck(BaseCheck):
    def run(self, table_name: str, timestamp_col: str = "updated_at", **kwargs) -> CheckResult:
        sql = f"SELECT MAX({timestamp_col}) FROM {table_name}"
        raw = self.connector.execute_scalar(sql)

        if raw is None:
            return CheckResult(
                check_name="freshness",
                table_name=table_name,
                passed=False,
                value=None,
                details={"error": f"No rows or NULL max({timestamp_col})"},
            )

        if isinstance(raw, str):
            max_ts = datetime.fromisoformat(raw)
        else:
            max_ts = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw))

        if max_ts.tzinfo is None:
            max_ts = max_ts.replace(tzinfo=timezone.utc)

        age_minutes = (datetime.now(timezone.utc) - max_ts).total_seconds() / 60

        return CheckResult(
            check_name="freshness",
            table_name=table_name,
            passed=True,
            value=round(age_minutes, 2),
            details={"max_timestamp": max_ts.isoformat(), "age_minutes": round(age_minutes, 2)},
        )
