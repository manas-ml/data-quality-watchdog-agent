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


class DbtTestResult(BaseModel):
    unique_id: str
    name: str
    status: Literal["pass", "fail", "error", "skipped"]
    failures: int = 0
    execution_time: float = 0.0
    test_type: str | None = None
    attached_model: str | None = None
    column: str | None = None
    compiled_code: str | None = None
    message: str | None = None


class DbtRunSummary(BaseModel):
    generated_at: str
    elapsed_time: float
    total_tests: int
    passed: int
    failed: int
    errored: int
    skipped: int
    test_results: list[DbtTestResult] = Field(default_factory=list)


class WatchdogConfig(BaseModel):
    table_name: str
    timestamp_col: str | None = None
    critical_cols: list[str] = Field(default_factory=list)
    custom_rules: list[CustomRule] = Field(default_factory=list)
    db_path: str = ":memory:"
    baseline_path: str = "baseline.db"
    anomaly_z_threshold: float = 3.0
    history_window: int = 30
    manifest_path: str | None = None
    run_results_path: str | None = None
