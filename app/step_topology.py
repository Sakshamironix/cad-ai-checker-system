"""Extract toroidal STEP topology deterministically."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
import cadquery as cq
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Torus

@dataclass(frozen=True)
class TorusFeature:
    face_index:int; major_radius_mm:float; minor_radius_mm:float
    @property
    def outer_diameter_mm(self)->float:return 2*(self.major_radius_mm+self.minor_radius_mm)
    @property
    def inner_diameter_mm(self)->float:return 2*(self.major_radius_mm-self.minor_radius_mm)
    def to_dict(self)->dict[str,object]:return asdict(self)|{"outer_diameter_mm":self.outer_diameter_mm,"inner_diameter_mm":self.inner_diameter_mm}

def extract_torus_features(data:bytes, filename:str)->tuple[TorusFeature,...]:
    suffix=Path(filename).suffix.lower()
    if suffix not in {".step",".stp"}: raise ValueError("Only .step and .stp files are supported.")
    temporary:Path|None=None
    try:
        with NamedTemporaryFile(suffix=suffix,delete=False) as handle: handle.write(data); temporary=Path(handle.name)
        shape=cq.importers.importStep(str(temporary)).val(); features=[]
        for index,face in enumerate(shape.Faces(),1):
            surface=BRepAdaptor_Surface(face.wrapped)
            if surface.GetType()==GeomAbs_Torus:
                torus=surface.Torus(); features.append(TorusFeature(index,float(torus.MajorRadius()),float(torus.MinorRadius())))
        return tuple(features)
    finally:
        if temporary: temporary.unlink(missing_ok=True)
