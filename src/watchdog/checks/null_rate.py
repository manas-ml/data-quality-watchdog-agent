from __future__ import annotations

from watchdog.checks.base import BaseCheck
from watchdog.models import CheckResult


class NullRateCheck(BaseCheck):
    def run(self, table_name: str, columns: list[str] | None = None, **kwargs) -> CheckResult:
        if not columns:
            return CheckResult(
                check_name="null_rate",
                table_name=table_name,
                passed=True,
                value=None,
                details={"message": "No columns specified"},
            )

        rates: dict[str, float] = {}
        for col in columns:
            sql = (
                f"SELECT COUNT(*) - COUNT({col}) AS nulls, COUNT(*) AS total"
                f" FROM {table_name}"
            )
            rows = self.connector.execute_rows(sql, limit=1)
            if rows:
                nulls = rows[0].get("nulls", 0) or 0
                total = rows[0].get("total", 1) or 1
                rates[col] = round(nulls / total * 100, 4)
            else:
                rates[col] = 0.0

        overall = max(rates.values()) if rates else 0.0
        return CheckResult(
            check_name="null_rate",
            table_name=table_name,
            passed=True,
            value=overall,
            details={"null_rates": rates},
        )
