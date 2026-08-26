from __future__ import annotations
from pathlib import Path
import ezdxf
from app.dxf_reader import analyze_dxf_file
from app.view_segmentation import assign_dimension_view, segment_views

def test_far_apart_geometry_is_separated_and_dimension_is_owned(tmp_path: Path) -> None:
    path=tmp_path / "views.dxf"; doc=ezdxf.new(); msp=doc.modelspace()
    msp.add_circle((0, 0), 10); msp.add_circle((100, 0), 10)
    dim=msp.add_linear_dim(base=(0, -15), p1=(-10, 0), p2=(10, 0), angle=0); dim.render(); doc.saveas(path)
    analysis=analyze_dxf_file(path); views=segment_views(analysis)
    assert len(views) == 2
    assert assign_dimension_view(analysis, views, analysis.dimensions[0].entity_index) == "VIEW-01"

def test_close_connected_geometry_is_one_view(tmp_path: Path) -> None:
    path=tmp_path / "one.dxf"; doc=ezdxf.new(); msp=doc.modelspace(); msp.add_line((0, 0), (10, 0)); msp.add_line((10, 0), (20, 0)); doc.saveas(path)
    assert len(segment_views(analyze_dxf_file(path))) == 1
