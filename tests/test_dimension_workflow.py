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
