from pathlib import Path
import cadquery as cq
import ezdxf
from app.dxf_reader import analyze_dxf_file
from app.profile_comparison import NG, compare_multiview_profiles
from app.view_classification import classify_views
from app.view_segmentation import segment_views

def test_unknown_view_is_explicit_ng(tmp_path: Path) -> None:
    dxf=tmp_path / "drawing.dxf"; doc=ezdxf.new(); doc.modelspace().add_circle((0,0),5); doc.saveas(dxf)
    step=tmp_path / "part.step"; cq.exporters.export(cq.Workplane("XY").circle(5).extrude(5), str(step), exportType="STEP")
    analysis=analyze_dxf_file(dxf); views=segment_views(analysis)
    result=compare_multiview_profiles(dxf.read_bytes(), dxf.name, step.read_bytes(), step.name, views, classify_views(analysis, views), 0.1)
    assert result[0].judgement == NG and "could not be deterministically classified" in result[0].warnings[0]
