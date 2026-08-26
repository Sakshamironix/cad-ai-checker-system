from pathlib import Path
import cadquery as cq
from app.step_section import generate_step_sections

def test_generates_three_centre_section_candidates(tmp_path: Path) -> None:
    path=tmp_path / "box.step"; cq.exporters.export(cq.Workplane("XY").box(10,20,30), str(path), exportType="STEP")
    assert {item.plane for item in generate_step_sections(path.read_bytes(), path.name)} == {"X-centre section", "Y-centre section", "Z-centre section"}
