import cadquery as cq
import numpy as np
import pytest
from app.geometry_check import project_visible,align_projection,bounds,unique_primitives
from app.projection import Point2D,ProjectedPrimitive
from app.visual_workspace import projection_sheet_layout,svg_projection_sheet

def test_rotated_extents_follow_actual_geometry():
    p=project_visible(cq.Workplane('XY').box(80,60,10).val(),'top')
    q=align_projection(p,p.primitives,quarter_turns=1,dx=17,dy=-4)
    assert (q.width,q.height)==pytest.approx((60,80))
    lo,hi=bounds(q.primitives)
    assert lo==pytest.approx(bounds(p.primitives)[0]+[17,-4])

def test_duplicate_hlr_lines_removed_but_distinct_arcs_preserved():
    a=ProjectedPrimitive('line',(Point2D(0,0),Point2D(5,0)))
    b=ProjectedPrimitive('line',a.points[::-1])
    c=ProjectedPrimitive('arc',(Point2D(1,0),Point2D(0,1),Point2D(-1,0)),Point2D(0,0),1)
    d=ProjectedPrimitive('arc',(Point2D(1,0),Point2D(0,-1),Point2D(-1,0)),Point2D(0,0),1)
    assert len(unique_primitives([a,b,c,d]))==3

def test_six_view_sheet_never_overlaps_or_mutates_projection_coordinates():
    shape=cq.Workplane('XY').box(80,60,10).val()
    projections=[project_visible(shape,v) for v in ['front','right','rear','top','left','bottom']]
    original=[p.primitives for p in projections]
    placements,*_=projection_sheet_layout(projections)
    envelopes=[]
    for p,x,y in placements:
        lo,hi=bounds(p.primitives);envelopes.append((lo+[x,y],hi+[x,y]))
    for i,(lo,hi) in enumerate(envelopes):
        for other_lo,other_hi in envelopes[i+1:]:
            assert np.any(hi<other_lo) or np.any(other_hi<lo)
    assert all(p.primitives==before for p,before in zip(projections,original))
    assert svg_projection_sheet(projections).count('<text ')==6

def test_circle_bounds_use_analytic_radius_not_sample_density():
    c=ProjectedPrimitive('circle',(Point2D(1,0),),Point2D(0,0),1)
    lo,hi=bounds((c,));assert lo==pytest.approx([-1,-1]);assert hi==pytest.approx([1,1])
