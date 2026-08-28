from __future__ import annotations

from app.step_measurements import measurable_features, measure_feature
from app.step_reader import HoleFeature, StepAnalysis, TorusFeature, TopologyCounts, Vector3D


def _step() -> StepAnalysis:
    return StepAnalysis("part.step",TopologyCounts(1,1,1,1,1),Vector3D(50,30,10),1,1,Vector3D(0,0,0),0,1,0,0,0,(HoleFeature(1,5,10),))


def test_measurements_are_step_geometry_values() -> None:
    features = measurable_features(_step())
    assert measure_feature(_step(), "EXTENT-X").value_mm == 50
    assert next(item for item in features if item.feature_id == "HOLE-01").value_mm == 10


def test_torus_measurements_are_geometry_derived() -> None:
    step = StepAnalysis("oring.step",TopologyCounts(1,1,1,1,1),Vector3D(7,7,2),1,1,Vector3D(0,0,0),0,0,2,0,0,(),tori=(TorusFeature(3,2.5,1.0),))
    assert measure_feature(step, "TORUS-01-INNER-DIA").value_mm == 3
    assert measure_feature(step, "TORUS-01-OUTER-DIA").value_mm == 7
    assert measure_feature(step, "TORUS-01-TUBE-RADIUS").value_mm == 1
