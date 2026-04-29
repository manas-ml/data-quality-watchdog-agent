from __future__ import annotations

from watchdog.checks.base import BaseCheck
from watchdog.models import CheckResult, ColumnDef


class SchemaDriftCheck(BaseCheck):
    def run(self, table_name: str, previous: list[ColumnDef] | None = None, **kwargs) -> CheckResult:
        current = self.connector.get_schema(table_name)
        current_map = {c.name: c for c in current}

        if previous is None:
            return CheckResult(
                check_name="schema_drift",
                table_name=table_name,
                passed=True,
                value=None,
                details={
                    "status": "no_baseline",
                    "current_columns": [c.model_dump() for c in current],
                },
            )

        previous_map = {c.name: c for c in previous}
        added = [n for n in current_map if n not in previous_map]
        removed = [n for n in previous_map if n not in current_map]
        type_changed = [
            n for n in current_map
            if n in previous_map and current_map[n].data_type != previous_map[n].data_type
        ]

        has_drift = bool(added or removed or type_changed)
        return CheckResult(
            check_name="schema_drift",
            table_name=table_name,
            passed=not has_drift,
            value=len(added) + len(removed) + len(type_changed),
            details={
                "added": added,
                "removed": removed,
                "type_changed": type_changed,
                "current_columns": [c.model_dump() for c in current],
            },
        )
