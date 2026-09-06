from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class MetricThresholds:
    valid_range: tuple[float, float]
    baseline: float
    spike_sigma: float
    drift_delta: float


@dataclass(frozen=True)
class ProcessorSettings:
    cycle_seconds: int
    drift_window: int
    gap_seconds: int
    spike_window: int
    thresholds: dict[str, MetricThresholds]


def load_settings(path: Path | None = None) -> ProcessorSettings:
    path = path or Path(__file__).parent / "config.yaml"
    doc = yaml.safe_load(path.read_text())
    thresholds = {
        metric: MetricThresholds(
            valid_range=(float(v["valid_range"][0]), float(v["valid_range"][1])),
            baseline=float(v["baseline"]),
            spike_sigma=float(v["spike_sigma"]),
            drift_delta=float(v["drift_delta"]),
        )
        for metric, v in doc["thresholds"].items()
    }
    return ProcessorSettings(
        cycle_seconds=int(doc["cycle_seconds"]),
        drift_window=int(doc["drift_window"]),
        gap_seconds=int(doc["gap_seconds"]),
        spike_window=int(doc["spike_window"]),
        thresholds=thresholds,
    )
