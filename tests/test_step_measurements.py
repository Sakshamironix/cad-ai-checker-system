from __future__ import annotations

from app.step_measurements import measurable_features, measure_feature
from app.step_reader import HoleFeature, StepAnalysis, TopologyCounts, Vector3D


def _step() -> StepAnalysis:
    return StepAnalysis("part.step",TopologyCounts(1,1,1,1,1),Vector3D(50,30,10),1,1,Vector3D(0,0,0),0,1,0,0,0,(HoleFeature(1,5,10),))


def test_measurements_are_step_geometry_values() -> None:
    features = measurable_features(_step())
    assert measure_feature(_step(), "EXTENT-X").value_mm == 50
    assert next(item for item in features if item.feature_id == "HOLE-01").value_mm == 10
