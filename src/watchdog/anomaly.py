from __future__ import annotations

import math

from watchdog.models import AnomalyScore


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _stddev(values: list[float], mu: float) -> float:
    variance = sum((v - mu) ** 2 for v in values) / len(values)
    return math.sqrt(variance)


def compute_anomaly_score(
    current: float,
    history: list[float],
    z_threshold: float = 3.0,
) -> AnomalyScore:
    """Z-score primary; percentage-change fallback when history < 5 points."""
    if len(history) < 2:
        return AnomalyScore(
            z_score=None,
            pct_change=None,
            is_anomaly=False,
            severity="INFO",
        )

    if len(history) >= 5:
        mu = _mean(history)
        sd = _stddev(history, mu)
        if sd == 0:
            z = 0.0
        else:
            z = (current - mu) / sd

        abs_z = abs(z)
        is_anomaly = abs_z >= z_threshold
        if abs_z < 2:
            severity = "INFO"
        elif abs_z < 3:
            severity = "WARNING"
        elif abs_z < 5:
            severity = "ALERT"
        else:
            severity = "CRITICAL"

        return AnomalyScore(
            z_score=round(z, 3),
            pct_change=None,
            is_anomaly=is_anomaly,
            severity=severity,
        )

    # Fallback: percentage change vs most recent historical value
    last = history[-1]
    if last == 0:
        pct = 0.0 if current == 0 else 100.0
    else:
        pct = abs(current - last) / abs(last) * 100

    if pct < 10:
        severity = "INFO"
    elif pct < 30:
        severity = "WARNING"
    elif pct < 70:
        severity = "ALERT"
    else:
        severity = "CRITICAL"

    return AnomalyScore(
        z_score=None,
        pct_change=round(pct, 2),
        is_anomaly=pct >= 30,
        severity=severity,
    )
