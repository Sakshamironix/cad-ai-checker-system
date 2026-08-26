from __future__ import annotations

from app.dimension_mapping import map_dimensions
from app.drawing_interpreter import DimensionRequirement, DrawingRequirements
from app.step_reader import HoleFeature, StepAnalysis, TopologyCounts, Vector3D


def _requirements(dimension: DimensionRequirement) -> DrawingRequirements:
    return DrawingRequirements("drawing.dxf","Millimetres",None,None,(dimension,),(),(),())


def _step(holes=()) -> StepAnalysis:
    return StepAnalysis("part.step",TopologyCounts(1,1,1,1,1),Vector3D(50,30,10),1,1,Vector3D(0,0,0),0,1,0,0,0,holes)


def test_diameter_maps_to_unique_hole() -> None:
    dimension = DimensionRequirement(1,"Diameter","diameter",20,None,None,None,None,"Millimetres","DIM",None,view_id="VIEW-01",requirement_id="DIM-001")
    result = map_dimensions(_requirements(dimension), _step((HoleFeature(1,10,20),)))
    assert result[0].status == "OK" and result[0].step_feature_id == "HOLE-01"


def test_ambiguous_holes_are_ng() -> None:
    dimension = DimensionRequirement(1,"Diameter","diameter",20,None,None,None,None,"Millimetres","DIM",None)
    result = map_dimensions(_requirements(dimension), _step((HoleFeature(1,10,20), HoleFeature(2,10,20))))
    assert result[0].status == "NG" and "Multiple" in result[0].reason
