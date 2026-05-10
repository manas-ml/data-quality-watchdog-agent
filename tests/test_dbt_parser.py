from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from watchdog.dbt.manifest import get_test_compiled_sql, parse_manifest
from watchdog.dbt.run_results import parse_run_results

# ---------------------------------------------------------------------------
# Minimal fixtures
# ---------------------------------------------------------------------------

MANIFEST = {
    "metadata": {
        "dbt_version": "1.7.0",
        "generated_at": "2024-01-01T00:00:00Z",
        "generated_by": "dbt",
    },
    "nodes": {
        "model.jaffle_shop.orders": {
            "unique_id": "model.jaffle_shop.orders",
            "name": "orders",
            "resource_type": "model",
            "schema": "main",
            "database": "dev",
            "alias": "orders",
            "config": {"materialized": "table"},
            "depends_on": {"nodes": ["model.jaffle_shop.stg_orders"]},
            "description": "One row per order.",
        },
        "model.jaffle_shop.stg_orders": {
            "unique_id": "model.jaffle_shop.stg_orders",
            "name": "stg_orders",
            "resource_type": "model",
            "schema": "main",
            "database": "dev",
            "alias": "stg_orders",
            "config": {"materialized": "view"},
            "depends_on": {"nodes": []},
            "description": "",
        },
        "test.jaffle_shop.not_null_orders_customer_id": {
            "unique_id": "test.jaffle_shop.not_null_orders_customer_id",
            "name": "not_null_orders_customer_id",
            "resource_type": "test",
            "schema": "main",
            "database": "dev",
            "test_metadata": {
                "name": "not_null",
                "kwargs": {"column_name": "customer_id", "model": "ref('orders')"},
            },
            "depends_on": {"nodes": ["model.jaffle_shop.orders"]},
            "compiled_code": "SELECT customer_id FROM orders WHERE customer_id IS NULL",
        },
        "test.jaffle_shop.unique_orders_order_id": {
            "unique_id": "test.jaffle_shop.unique_orders_order_id",
            "name": "unique_orders_order_id",
            "resource_type": "test",
            "schema": "main",
            "database": "dev",
            "test_metadata": {
                "name": "unique",
                "kwargs": {"column_name": "order_id", "model": "ref('orders')"},
            },
            "depends_on": {"nodes": ["model.jaffle_shop.orders"]},
            "compiled_code": "SELECT order_id FROM orders WHERE order_id IS NOT NULL GROUP BY order_id HAVING COUNT(*) > 1",
        },
    },
    "child_map": {
        "model.jaffle_shop.stg_orders": ["model.jaffle_shop.orders"],
        "model.jaffle_shop.orders": [
            "test.jaffle_shop.not_null_orders_customer_id",
            "test.jaffle_shop.unique_orders_order_id",
        ],
    },
}

RUN_RESULTS = {
    "metadata": {
        "dbt_version": "1.7.0",
        "generated_at": "2024-01-01T01:00:00Z",
    },
    "elapsed_time": 5.2,
    "results": [
        {
            "unique_id": "test.jaffle_shop.not_null_orders_customer_id",
            "status": "fail",
            "failures": 3,
            "execution_time": 0.45,
            "message": "Got 3 results, configured to fail if != 0",
        },
        {
            "unique_id": "test.jaffle_shop.unique_orders_order_id",
            "status": "pass",
            "failures": 0,
            "execution_time": 0.31,
            "message": "PASS",
        },
        {
            "unique_id": "model.jaffle_shop.orders",
            "status": "success",
            "failures": None,
            "execution_time": 1.2,
            "message": "CREATE TABLE (100 rows)",
        },
    ],
}


@pytest.fixture
def manifest_file(tmp_path: Path) -> str:
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(MANIFEST))
    return str(p)


@pytest.fixture
def run_results_file(tmp_path: Path) -> str:
    p = tmp_path / "run_results.json"
    p.write_text(json.dumps(RUN_RESULTS))
    return str(p)


# ---------------------------------------------------------------------------
# parse_manifest tests
# ---------------------------------------------------------------------------

class TestParseManifest:
    def test_extracts_models(self, manifest_file):
        result = parse_manifest(manifest_file)
        model_names = {m["name"] for m in result["models"]}
        assert model_names == {"orders", "stg_orders"}

    def test_extracts_tests(self, manifest_file):
        result = parse_manifest(manifest_file)
        test_names = {t["name"] for t in result["tests"]}
        assert "not_null_orders_customer_id" in test_names
        assert "unique_orders_order_id" in test_names

    def test_test_metadata_parsed(self, manifest_file):
        result = parse_manifest(manifest_file)
        nn_test = next(t for t in result["tests"] if t["name"] == "not_null_orders_customer_id")
        assert nn_test["test_type"] == "not_null"
        assert nn_test["column"] == "customer_id"
        assert nn_test["attached_model"] == "orders"
        assert "customer_id IS NULL" in nn_test["compiled_code"]

    def test_child_map_preserved(self, manifest_file):
        result = parse_manifest(manifest_file)
        assert "model.jaffle_shop.stg_orders" in result["child_map"]
        assert "model.jaffle_shop.orders" in result["child_map"]["model.jaffle_shop.stg_orders"]

    def test_dbt_version_in_metadata(self, manifest_file):
        result = parse_manifest(manifest_file)
        assert result["dbt_version"] == "1.7.0"


# ---------------------------------------------------------------------------
# get_test_compiled_sql tests
# ---------------------------------------------------------------------------

class TestGetTestCompiledSql:
    def test_returns_compiled_sql(self, manifest_file):
        result = get_test_compiled_sql(
            "test.jaffle_shop.not_null_orders_customer_id", manifest_file
        )
        assert result["test_type"] == "not_null"
        assert result["attached_model"] == "orders"
        assert result["column"] == "customer_id"
        assert "customer_id IS NULL" in result["compiled_code"]

    def test_unknown_test_returns_error(self, manifest_file):
        result = get_test_compiled_sql("test.jaffle_shop.nonexistent", manifest_file)
        assert "error" in result


# ---------------------------------------------------------------------------
# parse_run_results tests
# ---------------------------------------------------------------------------

class TestParseRunResults:
    def test_counts_statuses(self, run_results_file):
        result = parse_run_results(run_results_file)
        assert result["total_tests"] == 2
        assert result["passed"] == 1
        assert result["failed"] == 1
        assert result["errored"] == 0

    def test_model_results_separated(self, run_results_file):
        result = parse_run_results(run_results_file)
        assert len(result["model_results"]) == 1
        assert result["model_results"][0]["name"] == "orders"
        assert result["model_results"][0]["status"] == "success"

    def test_test_result_failure_count(self, run_results_file):
        result = parse_run_results(run_results_file)
        fail = next(r for r in result["test_results"] if r["status"] == "fail")
        assert fail["failures"] == 3

    def test_enriched_from_manifest(self, run_results_file, manifest_file):
        result = parse_run_results(run_results_file, manifest_file)
        fail = next(r for r in result["test_results"] if r["status"] == "fail")
        assert fail["test_type"] == "not_null"
        assert fail["column"] == "customer_id"
        assert fail["attached_model"] == "orders"
        assert fail["compiled_code"] is not None

    def test_without_manifest_still_works(self, run_results_file):
        result = parse_run_results(run_results_file)
        assert result["total_tests"] == 2
        for tr in result["test_results"]:
            assert tr["test_type"] is None

    def test_elapsed_time(self, run_results_file):
        result = parse_run_results(run_results_file)
        assert result["elapsed_time"] == pytest.approx(5.2)
