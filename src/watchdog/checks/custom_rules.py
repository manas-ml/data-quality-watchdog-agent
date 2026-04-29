from __future__ import annotations

from watchdog.checks.base import BaseCheck
from watchdog.models import CheckResult


class CustomRuleCheck(BaseCheck):
    def run(
        self,
        table_name: str,
        rule_name: str = "custom_rule",
        sql: str = "",
        threshold: int = 0,
        **kwargs,
    ) -> CheckResult:
        if not sql:
            return CheckResult(
                check_name=f"custom_rule:{rule_name}",
                table_name=table_name,
                passed=True,
                value=None,
                details={"error": "No SQL provided"},
            )

        try:
            rows = self.connector.execute_rows(sql, limit=5)
            violation_count = len(rows)

            count_sql = f"SELECT COUNT(*) FROM ({sql}) AS violations"
            total = self.connector.execute_scalar(count_sql)
            violation_count = int(total) if total is not None else len(rows)

            return CheckResult(
                check_name=f"custom_rule:{rule_name}",
                table_name=table_name,
                passed=violation_count <= threshold,
                value=float(violation_count),
                details={
                    "rule_name": rule_name,
                    "violation_count": violation_count,
                    "threshold": threshold,
                    "sample_violations": rows,
                },
            )
        except Exception as exc:
            return CheckResult(
                check_name=f"custom_rule:{rule_name}",
                table_name=table_name,
                passed=False,
                value=None,
                details={"error": str(exc)},
            )
