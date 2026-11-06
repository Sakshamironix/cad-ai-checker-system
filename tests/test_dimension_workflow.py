"""Real geometry regressions for formatted, multi-view O-ring dimensions."""
from dataclasses import replace
from io import StringIO
import cadquery as cq
import ezdxf
import pytest
from app.geometry_check import (load_drawing,load_solid,drawing_primitives,align_projection,
    check_dimension,suggest_projection,circular_features,unresolved_dimension,bounds)
from app.dxf_reader import analyze_dxf_bytes
from app.view_segmentation import segment_views


@pytest.fixture
def ring_pair(tmp_path):
    doc=ezdxf.new();doc.units=4;m=doc.modelspace()
    m.add_circle((0,0),3.5);m.add_arc((0,0),1.5,0,180);m.add_arc((0,0),1.5,180,360)
    m.add_line((14,-2.5),(14,2.5));m.add_line((16,-2.5),(16,2.5))
    m.add_arc((15,2.5),1,0,180);m.add_arc((15,-2.5),1,180,360)
    dims=[m.add_linear_dim(base=(20,0),p1=(16,-2.5),p2=(16,2.5),angle=90,text=r'\A1;<>',override={'dimdec':0}),
          m.add_radius_dim(center=(15,2.5),radius=1,angle=30,text=r'\A1;<>',override={'dimdec':0}),
          m.add_linear_dim(base=(0,-6),p1=(-1.5,0),p2=(1.5,0),text=r'\A1;\U+2205<>'),
          m.add_diameter_dim(center=(0,0),radius=3.5,angle=30,text=r'\A1;<>')]
    for d in dims:d.render()
    # Leader text can be closer to the other figure; the geometry anchor wins.
    dims[1].dimension.dxf.text_midpoint=(0,-12,0)
    stream=StringIO();doc.write(stream)
    path=tmp_path/'ring.step'
    cq.exporters.export(cq.Solid.makeTorus(2.5,1,dir=(1,0,0)),str(path))
    return stream.getvalue().encode(),path.read_bytes()


def inspect_pair(pair,confirmed=True,mode='nominal',override=None):
    db,sb=pair;doc=load_drawing(db);solid=load_solid(sb)
    if override is not None:list(doc.modelspace().query('DIMENSION'))[-1].dxf.text=override
    analysis=analyze_dxf_bytes(db,'ring.dxf')
    filtered=replace(analysis,entity_locations=tuple(x for x in analysis.entity_locations if x.entity_type in {'LINE','CIRCLE','ARC'}))
    views=segment_views(filtered,gap_mm=2);cache={};rows=[]
    for view in views:
        drawing=drawing_primitives(doc,set(view.entity_indexes))
        name=suggest_projection(solid,drawing,cache)
        projection=align_projection(cache['Projection',name,False],drawing)
        for index,entity in enumerate(doc.modelspace(),1):
            if index in view.dimension_indexes:
                rows.append(check_dimension(entity,'DIM-'+entity.dxf.handle,view.view_id,projection,drawing,1,None,confirmed,mode))
    return doc,views,rows


def test_formatted_ring_all_four_dimensions_are_assigned_and_measured(ring_pair):
    doc,views,rows=inspect_pair(ring_pair)
    assert len(views)==2 and len(rows)==4
    assert sorted(r.measured for r in rows)==pytest.approx([1,3,5,7])
    assert all(r.result=='OK' and r.nominal_result=='Match' for r in rows)
    assert all(r.tolerance_result=='Not specified' and r.lower is None and r.upper is None for r in rows)


def test_missing_tolerance_keeps_actual_measurements(ring_pair):
    _,_,rows=inspect_pair(ring_pair,mode='limits')
    assert len(rows)==4 and all(r.measured is not None and r.result=='NG' for r in rows)
    assert all(r.nominal_result=='Match' and r.tolerance_result=='Not specified' for r in rows)


def test_unconfirmed_alignment_shows_preliminary_values_without_a_pass(ring_pair):
    _,_,rows=inspect_pair(ring_pair,confirmed=False)
    assert len(rows)==4 and all(r.measured is not None and r.result=='NG' for r in rows)
    assert all('preliminary' in r.reason and r.nominal_result=='Not checked' for r in rows)


def test_wrong_nominal_is_not_used_to_choose_the_model_feature(ring_pair):
    _,_,rows=inspect_pair(ring_pair,override=r'\A1;6')
    row=next(r for r in rows if r.nominal==6)
    assert row.measured==pytest.approx(7) and row.result=='NG' and row.nominal_result=='Mismatch'


def test_unassigned_dimension_retains_drawing_nominal(ring_pair):
    doc=load_drawing(ring_pair[0]);entity=list(doc.modelspace().query('DIMENSION'))[-1]
    row=unresolved_dimension(entity,'DIM-004','Not assigned to a figure.')
    assert row.nominal==7 and row.measured is None and row.view=='Unassigned' and row.result=='NG'


def test_partial_arcs_never_become_a_full_circle():
    from app.projection import project_step_shape
    arcs=[project_step_shape(cq.Edge.makeCircle(2,angle1=a,angle2=b),'top').primitives[0]
          for a,b in [(0,90),(180,270)]]
    assert all(p.kind=='arc' for p in circular_features(arcs))
    lo,hi=bounds((arcs[0],))
    assert lo==pytest.approx([0,0],abs=1e-9) and hi==pytest.approx([2,2])


@pytest.mark.parametrize('width,height',[(140,60),(20,15)])
def test_changed_rectangle_geometry_retains_unscaled_model_measurement(width,height):
    from app.geometry_check import project_visible
    doc=ezdxf.new();m=doc.modelspace()
    m.add_lwpolyline([(0,0),(width,0),(width,height),(0,height)],close=True)
    d=m.add_linear_dim(base=(0,-5),p1=(0,0),p2=(width,0));d.render()
    drawing=drawing_primitives(doc,{1})
    solid=cq.Workplane('XY').box(80,60,10).val()
    projected=align_projection(project_visible(solid,'top'),drawing)
    row=check_dimension(d.dimension,'DIM-001','VIEW-01',projected,drawing,1,None,True,'nominal')
    assert row.nominal==width and row.measured==pytest.approx(80)
    assert row.result=='NG' and row.nominal_result=='Mismatch'
    assert any('topology' in f for f in row.features)
    assert projected.width==pytest.approx(80)  # no model scaling


def test_changed_concentric_diameters_match_inner_and_outer_roles_not_nearest_size():
    from app.geometry_check import project_visible
    doc=ezdxf.new();m=doc.modelspace();m.add_circle((0,0),3);m.add_circle((0,0),10)
    drawing=drawing_primitives(doc,{1,2})
    projection=align_projection(project_visible(cq.Solid.makeTorus(2.5,1),'top'),drawing)
    rows=[]
    for r in (3,10):
        d=m.add_diameter_dim(center=(0,0),radius=r,angle=30);d.render()
        rows.append(check_dimension(d.dimension,'DIM','VIEW',projection,drawing,1,None,True,'nominal'))
    assert [r.nominal for r in rows]==pytest.approx([6,20])
    assert [r.measured for r in rows]==pytest.approx([3,7])
    assert all(r.result=='NG' and r.nominal_result=='Mismatch' for r in rows)


def test_changed_capsule_geometry_measures_real_straight_length_and_radius():
    from app.geometry_check import project_visible
    doc=ezdxf.new();m=doc.modelspace()
    m.add_line((-4,-7),( -4,7));m.add_line((4,-7),(4,7))
    m.add_arc((0,7),4,0,180);m.add_arc((0,-7),4,180,360)
    drawing=drawing_primitives(doc,{1,2,3,4})
    projection=align_projection(project_visible(cq.Workplane('XY').slot2D(7,2,angle=90).extrude(2).val(),'top'),drawing)
    dims=[m.add_linear_dim(base=(7,0),p1=(4,-7),p2=(4,7),angle=90),
          m.add_radius_dim(center=(0,7),radius=4,angle=45)]
    rows=[]
    for d in dims:
        d.render();rows.append(check_dimension(d.dimension,'DIM','VIEW',projection,drawing,1,None,True,'nominal'))
    assert [r.nominal for r in rows]==pytest.approx([14,4])
    assert [r.measured for r in rows]==pytest.approx([5,1])
    assert all(r.result=='NG' and r.nominal_result=='Mismatch' for r in rows)


def test_different_topology_does_not_assign_an_unrelated_circle_by_size_rank():
    from app.geometry_check import profile_correspondence,project_visible
    doc=ezdxf.new();m=doc.modelspace();m.add_circle((0,0),10)
    drawing=drawing_primitives(doc,{1})
    projection=align_projection(project_visible(cq.Solid.makeTorus(2.5,1),'top'),drawing)
    assert profile_correspondence(drawing,projection.primitives) is None
    d=m.add_diameter_dim(center=(0,0),radius=10,angle=0);d.render()
    row=check_dimension(d.dimension,'DIM','VIEW',projection,drawing,1,None,True,'nominal')
    assert row.result=='NG' and row.measured is None and 'Cannot verify' in row.reason
