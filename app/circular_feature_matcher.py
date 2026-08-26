"""Deterministic semantic matching for annular and toroidal features."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from app.ring_features import RingFeature
from app.step_topology import TorusFeature

@dataclass(frozen=True)
class CircularFeatureMatch:
    drawing:RingFeature; model:TorusFeature; judgement:str; reason:str
    def to_dict(self)->dict[str,object]:return asdict(self)|{"drawing":self.drawing.to_dict(),"model":self.model.to_dict()}

def match_rings_to_tori(rings:tuple[RingFeature,...], tori:tuple[TorusFeature,...], tolerance_mm:float)->tuple[CircularFeatureMatch,...]:
    matches=[]; available=list(tori)
    for ring in rings:
        if not available:
            matches.append(CircularFeatureMatch(ring,TorusFeature(-1,0,0),"NG","No compatible STEP torus feature."));continue
        torus=min(available,key=lambda item:abs(item.outer_diameter_mm-ring.outer_diameter_mm)+abs(item.inner_diameter_mm-ring.inner_diameter_mm));available.remove(torus)
        okay=abs(torus.outer_diameter_mm-ring.outer_diameter_mm)<=tolerance_mm and abs(torus.inner_diameter_mm-ring.inner_diameter_mm)<=tolerance_mm
        matches.append(CircularFeatureMatch(ring,torus,"OK" if okay else "NG","Annular OD and ID are within tolerance." if okay else "Annular OD or ID is outside tolerance."))
    return tuple(matches)
