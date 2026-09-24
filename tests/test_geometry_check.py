from io import StringIO
from dataclasses import replace
import cadquery as cq
import ezdxf
import pytest
from app.geometry_check import (project_visible, align_projection, drawing_primitives,
    check_dimension, overall_result, load_drawing, load_solid, svg_overlay)
from app.step_section import section_shape
from app.projection import project_step_shape


def rectangle_doc():
    doc=ezdxf.new(); doc.units=4
    doc.modelspace().add_lwpolyline([(-40,-30),(40,-30),(40,30),(-40,30)],close=True)
    dim=doc.modelspace().add_linear_dim(base=(0,-40),p1=(-40,-30),p2=(40,-30),text='80 ±0.1')
    dim.render()
    return doc,dim.dimension


def check(solid,doc,dimension,confirmed=True,general=None):
    drawing=drawing_primitives(doc,{1})
    projection=align_projection(project_visible(solid,'top'),drawing)
    return check_dimension(dimension,'DIM-001','VIEW-01',projection,drawing,1.,general,confirmed)


def test_actual_geometry_pass_and_wrong_width_fail():
    doc,dim=rectangle_doc()
    good=check(cq.Workplane('XY').box(80,60,10).val(),doc,dim)
    bad=check(cq.Workplane('XY').box(80.5,60,10).val(),doc,dim)
    assert good.result=='OK' and good.measured==pytest.approx(80)
    assert bad.result=='NG' and bad.measured==pytest.approx(80.5)
    assert 'outside' in bad.reason


def test_matching_never_uses_overridden_nominal():
    doc,dim=rectangle_doc(); dim.dxf.text='60 ±0.1'
    row=check(cq.Workplane('XY').box(80,60,10).val(),doc,dim)
    assert row.measured==pytest.approx(80) and row.result=='NG'


def test_confirmation_missing_tolerance_and_empty_evidence_fail_closed():
    doc,dim=rectangle_doc(); shape=cq.Workplane('XY').box(80,60,10).val()
    assert check(shape,doc,dim,False).result=='NG'
    dim.dxf.text='<>'
    assert check(shape,doc,dim).result=='NG'
    assert check(shape,doc,dim,general=.1).result=='OK'
    assert overall_result([])=='NG'


def test_native_dimension_tolerance():
    doc,dim=rectangle_doc(); dim.dxf.text='<>'
    overrides=dim.override(); overrides.update({'dimtol':1,'dimtp':.2,'dimtm':.1}); overrides.commit()
    row=check(cq.Workplane('XY').box(80.15,60,10).val(),doc,dim)
    assert row.result=='OK' and row.tolerance_source=='DXF dimension style'


def test_section_is_actual_cut_not_projection():
    shape=cq.Workplane('XY').box(30,30,10).faces('>Z').workplane().hole(6,3).val()
    # Blind hole exists only in upper part; centre cut has no circular hole.
    assert project_visible(shape,'top').circle_count==1
    assert section_shape(shape,'Z',0).circle_count==0
    assert section_shape(shape,'Z',4).circle_count==1
    with pytest.raises(ValueError): section_shape(shape,'Z',100)


def test_torus_section_and_silhouette_are_real_geometry():
    shape=cq.Solid.makeTorus(2.5,1.)
    assert project_visible(shape,'top').circle_count==2
    cut=section_shape(shape,'Y',0)
    assert cut.circle_count==2
    assert sorted(p.radius for p in cut.primitives if p.kind=='circle')==pytest.approx([1.,1.])


def test_arc_is_not_expanded_into_full_circle():
    arc=cq.Edge.makeCircle(5,angle1=0,angle2=90)
    p=project_step_shape(arc,'top')
    assert p.circle_count==0
    assert len(p.primitives[0].points)>2


def test_hole_position_uses_anchors():
    doc=ezdxf.new(); doc.units=4; m=doc.modelspace()
    m.add_lwpolyline([(-40,-30),(40,-30),(40,30),(-40,30)],close=True)
    m.add_circle((10,0),4)
    d=m.add_linear_dim(base=(0,-40),p1=(-40,-30),p2=(10,0),angle=0,text='50 ±0.1');d.render()
    drawing=drawing_primitives(doc,{1,2})
    for xpos,expected in [(10,'OK'),(10.5,'NG')]:
        shape=cq.Workplane('XY').box(80,60,10).faces('>Z').workplane().center(xpos,0).hole(8).val()
        p=align_projection(project_visible(shape,'top'),drawing)
        row=check_dimension(d.dimension,'DIM-001','VIEW-01',p,drawing,1.,None,True)
        assert row.result==expected and row.measured==pytest.approx(40+xpos)


def test_spatial_circle_diameter_not_unrelated_equal_size():
    doc=ezdxf.new();doc.units=4;m=doc.modelspace()
    m.add_lwpolyline([(-40,-30),(40,-30),(40,30),(-40,30)],close=True)
    m.add_circle((10,0),4)
    d=m.add_diameter_dim(center=(10,0),radius=4,angle=0,text='8 ±0.1');d.render()
    shape=cq.Workplane('XY').box(80,60,10).faces('>Z').workplane().center(10,0).hole(8.4).val()
    drawing=drawing_primitives(doc,{1,2});p=align_projection(project_visible(shape,'top'),drawing)
    row=check_dimension(d.dimension,'DIM-001','VIEW-01',p,drawing,1.,None,True)
    assert row.measured==pytest.approx(8.4) and row.result=='NG'


def test_file_roundtrip_report_pipeline(tmp_path):
    from app.main import pdf_report
    from datetime import datetime,timezone
    doc,dim=rectangle_doc();dp=tmp_path/'plate.dxf';doc.saveas(dp)
    sp=tmp_path/'plate.step';cq.exporters.export(cq.Workplane('XY').box(80,60,10),str(sp))
    d=load_drawing(dp.read_bytes());s=load_solid(sp.read_bytes())
    row=check(s,d,list(d.modelspace().query('DIMENSION'))[0])
    assert row.result=='OK'
    payload={'result':overall_result([row]),'generated_at':datetime.now(timezone.utc).isoformat(),
        'drawing':'plate.dxf','model':'plate.step','drawing_sha256':'test','model_sha256':'test',
        'checks':[row.to_dict()],'views':[]}
    assert pdf_report(payload).startswith(b'%PDF')


def test_equidistant_landmarks_are_not_arbitrarily_matched():
    import numpy as np
    from app.geometry_check import associate
    with pytest.raises(ValueError, match='Ambiguous'):
        associate(np.array([0.,0.]),[(np.array([-1.,0.]),'A'),(np.array([1.,0.]),'B')],2.)


def test_radius_is_measured_from_real_torus_section():
    doc=ezdxf.new();doc.units=4;m=doc.modelspace()
    m.add_circle((-2.5,0),1);m.add_circle((2.5,0),1)
    d=m.add_radius_dim(center=(2.5,0),radius=1,angle=45,text='R1 ±0.05');d.render()
    drawing=drawing_primitives(doc,{1,2})
    projection=align_projection(section_shape(cq.Solid.makeTorus(2.5,1),'Y',0),drawing)
    row=check_dimension(d.dimension,'DIM-001','SECTION',projection,drawing,1.,None,True)
    assert row.result=='OK' and row.measured==pytest.approx(1.)


def test_elliptical_silhouette_is_not_a_circle():
    shape=cq.Workplane('XY').ellipse(10,5).extrude(3).val()
    assert project_visible(shape,'top').circle_count==0


def test_dashboard_upload_check_and_stale_report(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    import streamlit as st
    import io
    doc,_=rectangle_doc();dp=tmp_path/'plate.dxf';doc.saveas(dp)
    sp=tmp_path/'plate.step';cq.exporters.export(cq.Workplane('XY').box(80,60,10),str(sp))
    drawing=io.BytesIO(dp.read_bytes());drawing.name='plate.dxf'
    model=io.BytesIO(sp.read_bytes());model.name='plate.step'
    from streamlit.delta_generator import DeltaGenerator
    from pathlib import Path
    monkeypatch.setattr(DeltaGenerator,'file_uploader',lambda self,label,**kw: drawing if '2D' in label else model)
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app/main.py')).run(timeout=30)
    assert not app.exception
    for cb in app.checkbox:
        if cb.label.startswith('This view/section'): cb.check()
    app.run(timeout=30)
    app.button[0].click().run(timeout=30)
    assert not app.exception
    assert app.session_state['report']['result']=='OK'
    assert len(app.session_state['report']['checks'])==1
    # A new alignment must clear the old OK and require fresh confirmation.
    for widget in app.number_input:
        if widget.label=='Alignment X offset (mm)': widget.set_value(.5)
    app.run(timeout=30)
    assert not app.exception
    assert 'report' not in app.session_state
