from app.curve_reconstruction import ReconstructedCircle
from app.dxf_reader import Point2D
from app.ring_features import recognize_ring_features

def test_concentric_circles_form_one_annular_profile() -> None:
    features=recognize_ring_features((ReconstructedCircle(Point2D(0,0),25,(1,),True,360),ReconstructedCircle(Point2D(0,0),15,(2,),True,360)))
    assert len(features)==1 and features[0].outer_diameter_mm==50 and features[0].inner_diameter_mm==30

def test_eccentric_circles_do_not_form_annular_profile() -> None:
    features=recognize_ring_features((ReconstructedCircle(Point2D(0,0),25,(1,),True,360),ReconstructedCircle(Point2D(1,0),15,(2,),True,360)))
    assert features==()
