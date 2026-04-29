from __future__ import annotations

import pytest

from watchdog.checks.custom_rules import CustomRuleCheck
from watchdog.checks.freshness import FreshnessCheck
from watchdog.checks.null_rate import NullRateCheck
from watchdog.checks.schema_drift import SchemaDriftCheck
from watchdog.checks.volume import VolumeCheck
from watchdog.models import ColumnDef


class TestVolumeCheck:
    def test_returns_row_count(self, connector):
        result = VolumeCheck(connector).run("orders")
        assert result.check_name == "volume"
        assert result.value == 5.0
        assert result.passed is True

    def test_details_contain_row_count(self, connector):
        result = VolumeCheck(connector).run("orders")
        assert result.details["row_count"] == 5


class TestFreshnessCheck:
    def test_returns_age_in_minutes(self, connector):
        result = FreshnessCheck(connector).run("orders", timestamp_col="created_at")
        assert result.check_name == "freshness"
        assert result.passed is True
        assert isinstance(result.value, float)
        assert result.value > 0

    def test_details_include_age(self, connector):
        result = FreshnessCheck(connector).run("orders", timestamp_col="created_at")
        assert "age_minutes" in result.details
        assert "max_timestamp" in result.details


class TestNullRateCheck:
    def test_detects_null_customer_id(self, connector):
        result = NullRateCheck(connector).run("orders", columns=["customer_id"])
        rates = result.details["null_rates"]
        assert rates["customer_id"] == pytest.approx(20.0)  # 1 out of 5

    def test_detects_null_amount(self, connector):
        result = NullRateCheck(connector).run("orders", columns=["amount"])
        rates = result.details["null_rates"]
        assert rates["amount"] == pytest.approx(20.0)

    def test_no_columns_returns_pass(self, connector):
        result = NullRateCheck(connector).run("orders", columns=[])
        assert result.passed is True

    def test_multiple_columns(self, connector):
        result = NullRateCheck(connector).run("orders", columns=["customer_id", "amount"])
        assert "customer_id" in result.details["null_rates"]
        assert "amount" in result.details["null_rates"]


class TestSchemaDriftCheck:
    def test_no_baseline_returns_no_baseline_status(self, connector):
        result = SchemaDriftCheck(connector).run("orders", previous=None)
        assert result.details["status"] == "no_baseline"
        assert result.passed is True

    def test_no_drift_passes(self, connector):
        current = SchemaDriftCheck(connector).run("orders", previous=None)
        cols = [ColumnDef(**c) for c in current.details["current_columns"]]
        result = SchemaDriftCheck(connector).run("orders", previous=cols)
        assert result.passed is True
        assert result.details["added"] == []
        assert result.details["removed"] == []

    def test_detects_removed_column(self, connector):
        current = SchemaDriftCheck(connector).run("orders", previous=None)
        cols = [ColumnDef(**c) for c in current.details["current_columns"]]
        # Pretend "amount" existed before but is now gone
        extra = cols + [ColumnDef(name="amount_usd", data_type="DOUBLE", is_nullable=True)]
        result = SchemaDriftCheck(connector).run("orders", previous=extra)
        assert "amount_usd" in result.details["removed"]
        assert result.passed is False

    def test_detects_added_column(self, connector):
        current = SchemaDriftCheck(connector).run("orders", previous=None)
        cols = [ColumnDef(**c) for c in current.details["current_columns"]]
        # Remove one column from the "previous" snapshot so it appears added
        fewer = [c for c in cols if c.name != "status"]
        result = SchemaDriftCheck(connector).run("orders", previous=fewer)
        assert "status" in result.details["added"]


class TestCustomRuleCheck:
    def test_detects_negative_amounts(self, connector):
        result = CustomRuleCheck(connector).run(
            "orders",
            rule_name="negative_amounts",
            sql="SELECT * FROM orders WHERE amount < 0",
            threshold=0,
        )
        assert result.passed is False
        assert result.details["violation_count"] == 1

    def test_clean_rule_passes(self, connector):
        result = CustomRuleCheck(connector).run(
            "orders",
            rule_name="no_zero_ids",
            sql="SELECT * FROM orders WHERE order_id = 0",
            threshold=0,
        )
        assert result.passed is True
        assert result.details["violation_count"] == 0

    def test_invalid_sql_returns_error(self, connector):
        result = CustomRuleCheck(connector).run(
            "orders",
            rule_name="bad_sql",
            sql="SELECT * FROM nonexistent_table_xyz",
            threshold=0,
        )
        assert result.passed is False
        assert "error" in result.details
