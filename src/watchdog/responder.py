from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

_SEV_ORDER = {"INFO": 0, "WARNING": 1, "ALERT": 2, "CRITICAL": 3}
_SEV_ICON = {"INFO": "✓", "WARNING": "!", "ALERT": "▲", "CRITICAL": "✗"}


def _bar(char: str, width: int = 56) -> str:
    return char * width


def emit_report(report: dict) -> None:
    """Print a formatted quality report to stdout."""
    sev = report.get("overall_severity", "INFO")
    table = report.get("table", "unknown")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    findings: list[dict] = report.get("findings", [])
    root_cause: str = report.get("root_cause", "")
    action: str = report.get("recommended_action", "")

    width = 60
    border = "═" * width

    def row(text: str) -> str:
        pad = width - len(text) - 2
        return f"║ {text}{' ' * max(0, pad)} ║"

    lines = [
        f"╔{border}╗",
        row(f"DATA QUALITY REPORT"),
        f"╠{border}╣",
        row(f"Table    : {table}"),
        row(f"Severity : {_SEV_ICON.get(sev, '?')} {sev}"),
        row(f"Time     : {now}"),
        f"╠{border}╣",
        row("FINDINGS"),
        f"╠{border}╣",
    ]

    if findings:
        for f in findings:
            icon = _SEV_ICON.get(f.get("severity", "INFO"), "?")
            fsev = f.get("severity", "INFO")
            msg = f.get("message", "")
            lines.append(row(f"[{fsev}] {icon} {msg}"))
    else:
        lines.append(row("  No findings."))

    if root_cause:
        lines += [f"╠{border}╣", row("ROOT CAUSE"), f"╠{border}╣"]
        for chunk in _wrap(root_cause, width - 4):
            lines.append(row(f"  {chunk}"))

    if action:
        lines += [f"╠{border}╣", row("RECOMMENDED ACTION"), f"╠{border}╣"]
        for chunk in _wrap(action, width - 4):
            lines.append(row(f"  {chunk}"))

    lines.append(f"╚{border}╝")

    print("\n".join(lines))

    if report.get("parse_error"):
        print("\n[raw output from agent]")
        print(report.get("raw", ""))
    elif report.get("error"):
        print(f"\n[agent error] {report['error']}", file=sys.stderr)


def _wrap(text: str, width: int) -> list[str]:
    """Naive word-wrap."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 > width:
            if current:
                lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines or [""]
