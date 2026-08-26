from pathlib import Path
import cadquery as cq
from app.step_topology import extract_torus_features

def test_step_torus_is_recognized(tmp_path:Path)->None:
    # Build a native torus rather than revolving a profile on an offset plane:
    # the latter has CadQuery-version-dependent local-axis behaviour.
    path=tmp_path/"torus.step"; cq.exporters.export(cq.Workplane(obj=cq.Solid.makeTorus(20,5)),str(path),exportType="STEP")
    result=extract_torus_features(path.read_bytes(),path.name)
    assert result and result[0].major_radius_mm>0 and result[0].minor_radius_mm>0
