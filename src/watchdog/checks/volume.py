from __future__ import annotations

from watchdog.checks.base import BaseCheck
from watchdog.models import CheckResult


class VolumeCheck(BaseCheck):
    def run(self, table_name: str, **kwargs) -> CheckResult:
        count = self.connector.execute_scalar(f"SELECT COUNT(*) FROM {table_name}")
        row_count = int(count) if count is not None else 0

        return CheckResult(
            check_name="volume",
            table_name=table_name,
            passed=True,
            value=float(row_count),
            details={"row_count": row_count},
        )
