from __future__ import annotations
from pathlib import Path
import ezdxf
from app.dxf_reader import analyze_dxf_file
from app.view_classification import classify_views
from app.view_segmentation import segment_views

def test_section_needs_label_and_hatch_evidence(tmp_path: Path) -> None:
    path=tmp_path / "section.dxf"; doc=ezdxf.new(); msp=doc.modelspace(); msp.add_line((0, 0), (20, 0)); msp.add_text("SECTION A-A", dxfattribs={"insert": (2, 2)})
    hatch=msp.add_hatch(); hatch.paths.add_polyline_path([(0,0),(20,0),(20,10),(0,10)], is_closed=True); doc.saveas(path)
    analysis=analyze_dxf_file(path); result=classify_views(analysis, segment_views(analysis))
    assert result[0].detected_type == "Full section" and result[0].confidence == "High"
