"""Geometry-derived STEP measurements used by Milestone 15 mappings."""
from __future__ import annotations

from dataclasses import dataclass

from app.step_reader import StepAnalysis


@dataclass(frozen=True)
class StepMeasurement:
    feature_id: str
    feature_type: str
    value_mm: float
    evidence: str


def measurable_features(step: StepAnalysis) -> tuple[StepMeasurement, ...]:
    """Expose only measurements calculated from STEP B-rep analysis, never pixels."""
    features = [
        StepMeasurement("EXTENT-X", "overall width", step.bounding_box.x, "STEP bounding-box X extent"),
        StepMeasurement("EXTENT-Y", "overall height", step.bounding_box.y, "STEP bounding-box Y extent"),
        StepMeasurement("EXTENT-Z", "overall depth", step.bounding_box.z, "STEP bounding-box Z extent"),
    ]
    for index, hole in enumerate(step.holes, start=1):
        features.append(StepMeasurement(f"HOLE-{index:02d}", "through hole", hole.diameter, f"Reversed cylindrical STEP face {hole.face_index}"))
    for index, torus in enumerate(step.tori, start=1):
        prefix = f"TORUS-{index:02d}"
        evidence = f"Toroidal STEP face {torus.face_index}"
        features.extend((
            StepMeasurement(f"{prefix}-MEAN-DIA", "torus mean diameter", torus.mean_diameter, evidence),
            StepMeasurement(f"{prefix}-INNER-DIA", "torus inner diameter", torus.inner_diameter, evidence),
            StepMeasurement(f"{prefix}-OUTER-DIA", "torus outer diameter", torus.outer_diameter, evidence),
            StepMeasurement(f"{prefix}-TUBE-RADIUS", "torus tube radius", torus.minor_radius, evidence),
        ))
    return tuple(features)


def measure_feature(step: StepAnalysis, feature_id: str) -> StepMeasurement | None:
    """Return the named deterministic measurement when it exists."""
    return next((item for item in measurable_features(step) if item.feature_id == feature_id), None)
