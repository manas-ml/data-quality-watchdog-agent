from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ColumnDef(BaseModel):
    name: str
    data_type: str
    is_nullable: bool


class CustomRule(BaseModel):
    name: str
    sql: str
    threshold: int = 0


class CheckResult(BaseModel):
    check_name: str
    table_name: str
    passed: bool
    value: float | str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class AnomalyScore(BaseModel):
    z_score: float | None = None
    pct_change: float | None = None
    is_anomaly: bool
    severity: Literal["INFO", "WARNING", "ALERT", "CRITICAL"]


class WatchdogConfig(BaseModel):
    table_name: str
    timestamp_col: str | None = None
    critical_cols: list[str] = Field(default_factory=list)
    custom_rules: list[CustomRule] = Field(default_factory=list)
    db_path: str = ":memory:"
    baseline_path: str = "baseline.db"
    anomaly_z_threshold: float = 3.0
    history_window: int = 30
