"""Deterministic reconstruction of circular DXF curves from arcs and circles."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import math
from app.dxf_reader import ArcFeature, CircleFeature, Point2D

ANGLE_TOLERANCE_DEGREES = 1.0

@dataclass(frozen=True)
class ReconstructedCircle:
    center: Point2D; radius: float; source_entities: tuple[int, ...]; complete: bool; sweep_degrees: float
    def to_dict(self) -> dict[str, object]: return asdict(self)

def _sweep(arc: ArcFeature) -> float:
    value=(arc.end_angle-arc.start_angle)%360.0
    return 360.0 if math.isclose(value, 0.0) else value

def reconstruct_circles(circles: tuple[CircleFeature, ...], arcs: tuple[ArcFeature, ...], tolerance_mm: float = 0.05) -> tuple[ReconstructedCircle, ...]:
    """Merge compatible split arcs; duplicate/overlapping angular coverage is counted once."""
    result=[ReconstructedCircle(c.center,c.radius,(c.entity_index,),True,360.0) for c in circles]
    groups: list[list[ArcFeature]]=[]
    for arc in arcs:
        group=next((items for items in groups if math.hypot(items[0].center.x-arc.center.x, items[0].center.y-arc.center.y)<=tolerance_mm and abs(items[0].radius-arc.radius)<=tolerance_mm), None)
        if group is None: groups.append([arc])
        else: group.append(arc)
    for group in groups:
        coverage: list[tuple[float,float]]=[]
        for arc in group:
            start=arc.start_angle%360; end=start+_sweep(arc); coverage.append((start,end))
            if end>360: coverage.append((0.0,end-360))
        coverage.sort(); merged=[]
        for start,end in coverage:
            if not merged or start>merged[-1][1]+ANGLE_TOLERANCE_DEGREES: merged.append([start,end])
            else: merged[-1][1]=max(merged[-1][1],end)
        sweep=min(360.0,sum(end-start for start,end in merged))
        first=group[0]
        result.append(ReconstructedCircle(first.center,first.radius,tuple(sorted(arc.entity_index for arc in group)),sweep>=360.0-ANGLE_TOLERANCE_DEGREES,sweep))
    return tuple(result)
