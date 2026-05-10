from __future__ import annotations

import json
from pathlib import Path


def parse_manifest(manifest_path: str) -> dict:
    """Parse a dbt manifest.json and return project structure with models, tests, and lineage."""
    data = json.loads(Path(manifest_path).read_text())

    nodes = data.get("nodes", {})
    child_map = data.get("child_map", {})
    metadata = data.get("metadata", {})

    models = []
    tests = []

    for unique_id, node in nodes.items():
        resource_type = node.get("resource_type")

        if resource_type == "model":
            models.append({
                "unique_id": unique_id,
                "name": node.get("name"),
                "schema": node.get("schema"),
                "database": node.get("database"),
                "alias": node.get("alias", node.get("name")),
                "materialized": node.get("config", {}).get("materialized", "view"),
                "depends_on": node.get("depends_on", {}).get("nodes", []),
                "description": node.get("description", ""),
            })

        elif resource_type == "test":
            test_meta = node.get("test_metadata", {})
            kwargs = test_meta.get("kwargs", {})

            # Determine which model/column this test is attached to
            depends_on_nodes = node.get("depends_on", {}).get("nodes", [])
            attached_model = None
            for dep in depends_on_nodes:
                if dep.startswith("model."):
                    # Extract just the model name
                    attached_model = dep.split(".")[-1]
                    break

            tests.append({
                "unique_id": unique_id,
                "name": node.get("name"),
                "test_type": test_meta.get("name"),
                "attached_model": attached_model,
                "column": kwargs.get("column_name"),
                "kwargs": kwargs,
                "compiled_code": node.get("compiled_code") or node.get("compiled_sql"),
                "depends_on_nodes": depends_on_nodes,
                "schema": node.get("schema"),
            })

    return {
        "project_name": metadata.get("generated_by", data.get("metadata", {}).get("dbt_version", "unknown")),
        "dbt_version": metadata.get("dbt_version"),
        "generated_at": metadata.get("generated_at"),
        "models": models,
        "tests": tests,
        "child_map": child_map,
    }


def get_test_compiled_sql(test_unique_id: str, manifest_path: str) -> dict:
    """Return compiled SQL and metadata for a specific test node."""
    data = json.loads(Path(manifest_path).read_text())
    node = data.get("nodes", {}).get(test_unique_id)

    if node is None:
        return {"error": f"Test not found in manifest: {test_unique_id}"}

    test_meta = node.get("test_metadata", {})
    kwargs = test_meta.get("kwargs", {})
    depends_on_nodes = node.get("depends_on", {}).get("nodes", [])

    attached_model = None
    for dep in depends_on_nodes:
        if dep.startswith("model."):
            attached_model = dep.split(".")[-1]
            break

    return {
        "unique_id": test_unique_id,
        "name": node.get("name"),
        "test_type": test_meta.get("name"),
        "attached_model": attached_model,
        "column": kwargs.get("column_name"),
        "compiled_code": node.get("compiled_code") or node.get("compiled_sql"),
        "depends_on_nodes": depends_on_nodes,
        "schema": node.get("schema"),
        "database": node.get("database"),
    }
