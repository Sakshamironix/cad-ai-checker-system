from app.curve_reconstruction import reconstruct_circles
from app.dxf_reader import ArcFeature, CircleFeature, Point2D

def _arc(index:int,start:float,end:float)->ArcFeature:return ArcFeature(index,"0",Point2D(0,0),10,start,end)

def test_four_split_arcs_reconstruct_one_complete_circle() -> None:
    result=reconstruct_circles((),tuple(_arc(index,index*90,(index+1)*90) for index in range(4)))
    assert len(result)==1 and result[0].complete and result[0].sweep_degrees==360

def test_partial_arc_stays_open() -> None:
    result=reconstruct_circles((),(_arc(1,0,180),))
    assert not result[0].complete and result[0].sweep_degrees==180

def test_explicit_circle_is_complete() -> None:
    result=reconstruct_circles((CircleFeature(1,"0",Point2D(0,0),10,20),),())
    assert result[0].complete
