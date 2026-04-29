from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from watchdog.agent import run_watchdog
from watchdog.models import WatchdogConfig


def _make_text_block(text: str):
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _make_tool_use_block(block_id: str, name: str, inputs: dict):
    block = MagicMock()
    block.type = "tool_use"
    block.id = block_id
    block.name = name
    block.input = inputs
    return block


def _make_response(content, stop_reason="end_turn"):
    response = MagicMock()
    response.content = content
    response.stop_reason = stop_reason
    return response


class TestAgentLoop:
    def _config(self, db_path=":memory:", baseline_path=":memory:") -> WatchdogConfig:
        return WatchdogConfig(
            table_name="orders",
            db_path=db_path,
            baseline_path=baseline_path,
        )

    def test_returns_dict_on_clean_json_response(self, tmp_path):
        report = {
            "table": "orders",
            "overall_severity": "INFO",
            "findings": [],
            "root_cause": "All checks passed.",
            "recommended_action": "No action required.",
        }
        final_response = _make_response([_make_text_block(json.dumps(report))])

        config = self._config(baseline_path=str(tmp_path / "b.db"))

        with patch("watchdog.agent.anthropic.Anthropic") as MockClient, \
             patch("watchdog.agent.DuckDBConnector") as MockConnector:
            mock_conn = MagicMock()
            mock_conn.execute_scalar.return_value = 100
            mock_conn.execute_rows.return_value = []
            mock_conn.get_schema.return_value = []
            MockConnector.return_value = mock_conn

            mock_client = MagicMock()
            MockClient.return_value = mock_client
            mock_client.messages.create.return_value = final_response

            result = run_watchdog(config)

        assert result["table"] == "orders"
        assert result["overall_severity"] == "INFO"

    def test_dispatches_tool_calls_before_final_response(self, tmp_path):
        """Agent should process tool_use turns before end_turn."""
        volume_tool = _make_tool_use_block("t1", "get_row_count", {"table_name": "orders"})
        tool_response = _make_response([volume_tool], stop_reason="tool_use")

        report = {"table": "orders", "overall_severity": "INFO", "findings": []}
        final_response = _make_response([_make_text_block(json.dumps(report))])

        config = self._config(baseline_path=str(tmp_path / "b.db"))

        with patch("watchdog.agent.anthropic.Anthropic") as MockClient, \
             patch("watchdog.agent.DuckDBConnector") as MockConnector:
            mock_conn = MagicMock()
            mock_conn.execute_scalar.return_value = 42
            mock_conn.execute_rows.return_value = []
            mock_conn.get_schema.return_value = []
            MockConnector.return_value = mock_conn

            mock_client = MagicMock()
            MockClient.return_value = mock_client
            mock_client.messages.create.side_effect = [tool_response, final_response]

            result = run_watchdog(config)

        assert mock_client.messages.create.call_count == 2
        assert result["overall_severity"] == "INFO"

    def test_handles_json_in_code_fence(self, tmp_path):
        """Agent output wrapped in ```json ... ``` should still parse."""
        report = {"table": "orders", "overall_severity": "WARNING", "findings": []}
        fenced = f"```json\n{json.dumps(report)}\n```"
        final_response = _make_response([_make_text_block(fenced)])

        config = self._config(baseline_path=str(tmp_path / "b.db"))

        with patch("watchdog.agent.anthropic.Anthropic") as MockClient, \
             patch("watchdog.agent.DuckDBConnector") as MockConnector:
            mock_conn = MagicMock()
            mock_conn.execute_scalar.return_value = 10
            mock_conn.execute_rows.return_value = []
            mock_conn.get_schema.return_value = []
            MockConnector.return_value = mock_conn

            mock_client = MagicMock()
            MockClient.return_value = mock_client
            mock_client.messages.create.return_value = final_response

            result = run_watchdog(config)

        assert result["overall_severity"] == "WARNING"
