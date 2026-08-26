from pathlib import Path
import cadquery as cq
from app.step_topology import extract_torus_features

def test_step_torus_is_recognized(tmp_path:Path)->None:
    path=tmp_path/"torus.step"; cq.exporters.export(cq.Workplane("XZ").workplane(offset=20).circle(5).revolve(360,(0,0,0),(0,1,0)),str(path),exportType="STEP")
    result=extract_torus_features(path.read_bytes(),path.name)
    assert result and result[0].major_radius_mm>0 and result[0].minor_radius_mm>0
