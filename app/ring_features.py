"""Topology-aware circular and annular feature recognition."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import math
from app.curve_reconstruction import ReconstructedCircle
from app.dxf_reader import Point2D

@dataclass(frozen=True)
class RingFeature:
    center: Point2D; outer_radius_mm: float; inner_radius_mm: float; source_entities: tuple[int, ...]; kind: str = "annular profile"
    @property
    def outer_diameter_mm(self)->float: return self.outer_radius_mm*2
    @property
    def inner_diameter_mm(self)->float: return self.inner_radius_mm*2
    @property
    def radial_width_mm(self)->float: return self.outer_radius_mm-self.inner_radius_mm
    def to_dict(self)->dict[str,object]: return asdict(self)|{"outer_diameter_mm":self.outer_diameter_mm,"inner_diameter_mm":self.inner_diameter_mm,"radial_width_mm":self.radial_width_mm}

def recognize_ring_features(curves: tuple[ReconstructedCircle,...], tolerance_mm: float=0.05)->tuple[RingFeature,...]:
    """Pair complete concentric boundaries once, preventing nested-circle double counts."""
    complete=[item for item in curves if item.complete]; rings=[]; used=set()
    for index, outer in enumerate(sorted(complete,key=lambda item:item.radius,reverse=True)):
        if id(outer) in used: continue
        inners=[item for item in complete if item.radius<outer.radius-tolerance_mm and math.hypot(item.center.x-outer.center.x,item.center.y-outer.center.y)<=tolerance_mm]
        if not inners: continue
        inner=max(inners,key=lambda item:item.radius); used.update({id(outer),id(inner)})
        rings.append(RingFeature(outer.center,outer.radius,inner.radius,tuple(sorted((*outer.source_entities,*inner.source_entities)))))
    return tuple(rings)
