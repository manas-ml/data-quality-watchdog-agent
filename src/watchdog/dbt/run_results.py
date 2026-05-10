from __future__ import annotations

import json
from pathlib import Path


def parse_run_results(run_results_path: str, manifest_path: str | None = None) -> dict:
    """Parse a dbt run_results.json and return a structured summary.

    If manifest_path is provided, enriches each test result with test_type,
    attached_model, column, and compiled_code from the manifest.
    """
    data = json.loads(Path(run_results_path).read_text())

    # Load manifest index for enrichment
    manifest_nodes: dict = {}
    if manifest_path:
        manifest_data = json.loads(Path(manifest_path).read_text())
        manifest_nodes = manifest_data.get("nodes", {})

    metadata = data.get("metadata", {})
    results = data.get("results", [])

    test_results = []
    model_results = []

    passed = failed = errored = skipped = 0

    for result in results:
        unique_id = result.get("unique_id", "")
        resource_type = result.get("unique_id", "").split(".")[0] if "." in unique_id else ""
        status = result.get("status", "")

        # Normalise status strings across dbt versions
        # Models use "success"/"error"; tests use "pass"/"fail"/"error"
        is_test = unique_id.startswith("test.")

        if is_test:
            if status == "pass":
                passed += 1
            elif status == "fail":
                failed += 1
            elif status == "error":
                errored += 1
            elif status == "skipped":
                skipped += 1

            # Enrich from manifest
            manifest_node = manifest_nodes.get(unique_id, {})
            test_meta = manifest_node.get("test_metadata", {})
            kwargs = test_meta.get("kwargs", {})
            depends_on_nodes = manifest_node.get("depends_on", {}).get("nodes", [])

            attached_model = None
            for dep in depends_on_nodes:
                if dep.startswith("model."):
                    attached_model = dep.split(".")[-1]
                    break

            # failures count: dbt v1 uses "failures", some versions expose it differently
            failures = result.get("failures") or 0
            if failures is None:
                failures = 0

            test_results.append({
                "unique_id": unique_id,
                "name": result.get("unique_id", "").split(".")[-1],
                "status": status,
                "failures": int(failures),
                "execution_time": result.get("execution_time", 0.0),
                "message": result.get("message"),
                "test_type": test_meta.get("name") if manifest_node else None,
                "attached_model": attached_model,
                "column": kwargs.get("column_name"),
                "compiled_code": (
                    manifest_node.get("compiled_code") or manifest_node.get("compiled_sql")
                    if manifest_node else result.get("compiled_code")
                ),
            })
        else:
            # Model result
            model_results.append({
                "unique_id": unique_id,
                "name": unique_id.split(".")[-1],
                "status": status,
                "execution_time": result.get("execution_time", 0.0),
                "message": result.get("message"),
            })

    total_tests = passed + failed + errored + skipped

    return {
        "generated_at": metadata.get("generated_at", ""),
        "elapsed_time": data.get("elapsed_time", 0.0),
        "dbt_version": metadata.get("dbt_version"),
        "total_tests": total_tests,
        "passed": passed,
        "failed": failed,
        "errored": errored,
        "skipped": skipped,
        "test_results": test_results,
        "model_results": model_results,
    }
