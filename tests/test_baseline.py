from __future__ import annotations

from watchdog.baseline.store import BaselineStore
from watchdog.models import ColumnDef


class TestBaselineStore:
    def test_record_and_retrieve_metric(self, baseline: BaselineStore):
        baseline.record_metric("orders", "row_count", 1000.0)
        history = baseline.get_history("orders", "row_count")
        assert history == [1000.0]

    def test_history_window_limits_results(self, baseline: BaselineStore):
        for i in range(10):
            baseline.record_metric("orders", "row_count", float(i * 100))
        history = baseline.get_history("orders", "row_count", window=5)
        assert len(history) == 5

    def test_history_is_chronological(self, baseline: BaselineStore):
        for val in [100.0, 200.0, 300.0]:
            baseline.record_metric("orders", "row_count", val)
        history = baseline.get_history("orders", "row_count")
        assert history == [100.0, 200.0, 300.0]

    def test_column_level_metric(self, baseline: BaselineStore):
        baseline.record_metric("orders", "null_rate", 5.0, column_name="customer_id")
        baseline.record_metric("orders", "null_rate", 1.0, column_name="amount")
        h1 = baseline.get_history("orders", "null_rate", column_name="customer_id")
        h2 = baseline.get_history("orders", "null_rate", column_name="amount")
        assert h1 == [5.0]
        assert h2 == [1.0]

    def test_no_history_returns_empty_list(self, baseline: BaselineStore):
        history = baseline.get_history("nonexistent_table", "row_count")
        assert history == []

    def test_schema_roundtrip(self, baseline: BaselineStore):
        cols = [
            ColumnDef(name="id", data_type="INTEGER", is_nullable=False),
            ColumnDef(name="name", data_type="VARCHAR", is_nullable=True),
        ]
        baseline.record_schema("customers", cols)
        retrieved = baseline.get_last_schema("customers")
        assert retrieved is not None
        assert len(retrieved) == 2
        assert retrieved[0].name == "id"
        assert retrieved[1].data_type == "VARCHAR"

    def test_get_last_schema_returns_most_recent(self, baseline: BaselineStore):
        old_cols = [ColumnDef(name="id", data_type="INTEGER", is_nullable=False)]
        new_cols = [
            ColumnDef(name="id", data_type="INTEGER", is_nullable=False),
            ColumnDef(name="email", data_type="VARCHAR", is_nullable=True),
        ]
        baseline.record_schema("users", old_cols)
        baseline.record_schema("users", new_cols)
        retrieved = baseline.get_last_schema("users")
        assert retrieved is not None
        assert len(retrieved) == 2

    def test_get_last_schema_returns_none_when_empty(self, baseline: BaselineStore):
        assert baseline.get_last_schema("phantom_table") is None
