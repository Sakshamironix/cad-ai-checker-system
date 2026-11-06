"""Figure-based dimension checking. Nominal values NEVER select model features.

The caller selects a projection/section and confirms its rigid alignment. Dimension
anchors are associated spatially to projected vertices/centres. Ambiguous or
unsupported evidence is NG (cannot verify), not an invented measurement.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass, replace
from io import StringIO
from tempfile import NamedTemporaryFile
import math
import cadquery as cq
import ezdxf
import numpy as np
from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
from OCP.BRepLib import BRepLib
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Torus
from app.projection import Point2D, ProjectedPrimitive, StepProjection, project_step_shape
from app.profile_comparison import _entity_primitives
from app.drawing_interpreter import parse_checked_dimension_text, ParsedDimensionText, _normalize_text
from app.runtime_limits import load_runtime_limits

ENGINE_VERSION = '0.19.1-geometry'

@dataclass(frozen=True)
class DimensionCheck:
    dimension: str
    view: str
    kind: str
    nominal: float | None
    measured: float | None
    lower: float | None
    upper: float | None
    result: str
    reason: str
    features: tuple[str, ...] = ()
    anchors: tuple[tuple[float, float], ...] = ()
    tolerance_source: str = 'Unavailable'
    nominal_result: str = 'Not checked'
    tolerance_result: str = 'Not checked'
    def to_dict(self):
        return asdict(self)


def load_drawing(data: bytes):
    if not data or len(data) > load_runtime_limits().max_dxf_bytes:
        raise ValueError('DXF is empty or exceeds the upload limit.')
    with NamedTemporaryFile(suffix='.dxf') as f:
        f.write(data); f.flush()
        doc = ezdxf.readfile(f.name)
    if int(doc.header.get('$INSUNITS', 0)) not in (0, 4):
        raise ValueError('This initial release requires a millimetre DXF. Convert its units before checking.')
    if len(doc.modelspace()) > load_runtime_limits().max_dxf_entities:
        raise ValueError('DXF exceeds the entity limit.')
    return doc


def load_solid(data: bytes):
    if not data or len(data) > load_runtime_limits().max_step_bytes:
        raise ValueError('STEP is empty or exceeds the upload limit.')
    with NamedTemporaryFile(suffix='.step') as f:
        f.write(data); f.flush()
        imported = cq.importers.importStep(f.name)
        roots = imported.vals()
        shape = roots[0] if len(roots)==1 else cq.Compound.makeCompound(roots)
    if not shape.Solids() or not shape.isValid():
        raise ValueError('A valid STEP solid is required.')
    return shape


def project_visible(shape, view: str, include_hidden: bool = False) -> StepProjection:
    """OpenCASCADE orthographic HLR, including curved-surface silhouettes."""
    directions = {
        'top': ((0, 0, 1), (1, 0, 0)), 'front': ((0, -1, 0), (1, 0, 0)),
        'right': ((1, 0, 0), (0, 1, 0)), 'bottom': ((0, 0, -1), (-1, 0, 0)),
        'rear': ((0, 1, 0), (-1, 0, 0)), 'left': ((-1, 0, 0), (0, -1, 0)),
    }
    normal, xaxis = directions[view]
    hlr = HLRBRep_Algo(); hlr.Add(shape.wrapped)
    hlr.Projector(HLRAlgo_Projector(gp_Ax2(gp_Pnt(), gp_Dir(*normal), gp_Dir(*xaxis))))
    hlr.Update(); hlr.Hide()
    result = HLRBRep_HLRToShape(hlr)
    compounds = [result.VCompound(), result.Rg1LineVCompound(), result.OutLineVCompound()]
    if include_hidden:
        compounds += [result.HCompound(), result.OutLineHCompound()]
    shapes = []
    for item in compounds:
        if not item.IsNull():
            BRepLib.BuildCurves3d_s(item, 1e-7)
            shapes.append(cq.Shape.cast(item))
    if not shapes:
        raise ValueError('The selected STEP view contains no projected edges.')
    p = project_step_shape(cq.Compound.makeCompound(shapes), 'top')
    analytic_circles = []; analytic_caps=[]
    yaxis = np.cross(normal, xaxis)
    for face in shape.Faces():
        surface = BRepAdaptor_Surface(face.wrapped)
        if surface.GetType() != GeomAbs_Torus:
            continue
        torus = surface.Torus(); direction = torus.Axis().Direction()
        axis=np.array([direction.X(),direction.Y(),direction.Z()]); c=torus.Location();xyz=np.array([c.X(),c.Y(),c.Z()])
        # Side-on torus silhouettes have circular end caps even if HLR emits
        # approximate B-splines. Recover only from the analytic surface and
        # observed edge samples; trimmed angular coverage remains unchanged.
        if abs(np.dot(axis,normal))<1e-9:
            radial=np.cross(axis,normal);radial/=np.linalg.norm(radial)
            for sign in (-1,1):
                cap=xyz+sign*torus.MajorRadius()*radial
                analytic_caps.append((np.array([np.dot(cap,xaxis),np.dot(cap,yaxis)]),torus.MinorRadius()))
        if any(abs(upper-lower-2*math.pi) > 1e-6 for lower,upper in
               [(surface.FirstUParameter(),surface.LastUParameter()),
                (surface.FirstVParameter(),surface.LastVParameter())]):
            continue
        torus = surface.Torus(); direction = torus.Axis().Direction()
        if abs(np.dot([direction.X(),direction.Y(),direction.Z()],normal)) < .999999:
            continue
        c = torus.Location(); xyz = [c.X(),c.Y(),c.Z()]
        centre = np.array([np.dot(xyz,xaxis),np.dot(xyz,yaxis)])
        for radius in (torus.MajorRadius()+torus.MinorRadius(),torus.MajorRadius()-torus.MinorRadius()):
            if radius > 0: analytic_circles.append((centre,radius))
    # HLR can encode a circular silhouette as a closed B-spline. Recognize it
    # only if every sampled point satisfies a circle to kernel-scale precision.
    normalized = []
    for primitive in p.primitives:
        pts = np.array([(q.x, q.y) for q in primitive.points])
        if primitive.kind=='curve' and len(pts)>=8:
            candidates={(tuple(np.round(centre,9)),round(radius,9)) for centre,radius in analytic_caps
                        if np.max(np.abs(np.linalg.norm(pts-centre,axis=1)-radius))<1e-3}
            if len(candidates)==1:
                centre,radius=next(iter(candidates))
                primitive=replace(primitive,kind='arc',center=Point2D(*centre),radius=radius)
        if primitive.kind == 'curve' and len(pts) >= 32 and np.linalg.norm(pts[0]-pts[-1]) < 1e-7:
            # HLR torus outlines can be approximate B-splines. Recover the
            # exact circle only from the corresponding analytic STEP surface.
            for centre, radius in analytic_circles:
                if np.max(np.abs(np.linalg.norm(pts-centre,axis=1)-radius)) < 1e-3:
                    primitive = replace(primitive, kind='circle', center=Point2D(*centre), radius=radius)
            matrix = np.column_stack((2*pts[:,0], 2*pts[:,1], np.ones(len(pts))))
            solution, _, rank, _ = np.linalg.lstsq(matrix, (pts*pts).sum(axis=1), rcond=None)
            centre = solution[:2]
            radii = np.linalg.norm(pts-centre, axis=1)
            angles = np.unwrap(np.arctan2(pts[:,1]-centre[1], pts[:,0]-centre[0]))
            if rank == 3 and np.ptp(radii) < 1e-7 and abs(abs(angles[-1]-angles[0])-2*math.pi) < 1e-6:
                primitive = replace(primitive, kind='circle', center=Point2D(*centre), radius=float(radii.mean()))
        normalized.append(primitive)
    primitives = unique_primitives(normalized)
    lo, hi = bounds(primitives)
    return replace(p, view=view, primitives=primitives, width=float(hi[0]-lo[0]), height=float(hi[1]-lo[1]))


def unique_primitives(primitives):
    """Remove coincident HLR edges emitted by multiple visibility compounds.

    Keep distinct arcs of the same circle. This is display/topology cleanup,
    never a nominal-dimension or tolerance-based geometry merge.
    """
    result=[]; seen=set()
    def point(q): return (round(q.x,7),round(q.y,7))
    for p in primitives:
        if p.kind=='circle' and p.center is not None:
            key=('circle',point(p.center),round(p.radius,7))
        elif p.kind=='line' and p.points:
            key=('line',tuple(sorted([point(p.points[0]),point(p.points[-1])])) )
        else:
            samples=tuple(point(q) for q in p.points)
            key=(p.kind,min(samples,samples[::-1]))
        if key not in seen: result.append(p);seen.add(key)
    return tuple(result)


def bounds(primitives):
    coords=[(p.x,p.y) for item in primitives for p in item.points]
    for item in primitives:
        if item.kind=='circle' and item.center is not None:
            x,y,r=item.center.x,item.center.y,item.radius
            coords.extend([(x-r,y-r),(x+r,y+r)])
        elif item.kind=='arc' and item.center is not None:
            for angle in (0,math.pi/2,math.pi,3*math.pi/2):
                q=np.array([item.center.x+item.radius*math.cos(angle),item.center.y+item.radius*math.sin(angle)])
                if circular_anchor_on_sweep(item,q):coords.append(tuple(q))
    points = np.array(coords)
    if not len(points):
        raise ValueError('No drawing geometry selected. Check layer and view filters.')
    return points.min(axis=0), points.max(axis=0)


def drawing_primitives(doc, indexes, excluded_layers=()):
    selected = [e for i,e in enumerate(doc.modelspace(),1) if i in indexes and e.dxf.layer not in excluded_layers]
    elevations=[]
    def validate_plane(entity):
        if not np.allclose(tuple(entity.dxf.get('extrusion',(0,0,1))), (0,0,1), rtol=0, atol=1e-9):
            raise ValueError('Non-XY drawing extrusion is not supported. Flatten the selected DXF view first.')
        if entity.dxftype() in {'LWPOLYLINE','POLYLINE'}:
            for virtual in entity.virtual_entities(): validate_plane(virtual)
        elif entity.dxftype() in {'LINE','ARC','CIRCLE'}:
            for name in ('start','end','center'):
                if entity.dxf.hasattr(name): elevations.append(float(entity.dxf.get(name).z))
        elif entity.dxftype()=='SPLINE':
            elevations.extend(float(p[2]) for p in entity.control_points)
    for entity in selected: validate_plane(entity)
    if elevations and max(elevations)-min(elevations)>1e-7:
        raise ValueError('The selected drawing view is not planar in XY. Flatten its geometry before checking.')
    return tuple(p for e in selected for p in _entity_primitives(e))


def align_projection(projection, drawing, quarter_turns=0, dx=0., dy=0.):
    """Rigid transform only. Never scale a STEP model to fit a drawing."""
    angle = quarter_turns * math.pi / 2
    mat = np.array([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])
    def rotate(p):
        v = mat @ np.array([p.x, p.y]); return Point2D(*v)
    rotated = tuple(replace(p, points=tuple(rotate(q) for q in p.points),
                            center=rotate(p.center) if p.center else None) for p in projection.primitives)
    low, _ = bounds(rotated); drawing_low, _ = bounds(drawing)
    shift = drawing_low - low + np.array([dx, dy])
    def move(p): return Point2D(p.x + shift[0], p.y + shift[1])
    aligned=tuple(replace(p, points=tuple(move(q) for q in p.points),
                   center=move(p.center) if p.center else None) for p in rotated)
    lo,hi=bounds(aligned)
    return replace(projection, primitives=aligned,width=float(hi[0]-lo[0]),height=float(hi[1]-lo[1]))


def landmarks(primitives):
    result = []
    for i, p in enumerate(primitives, 1):
        label = f'EDGE-{i:03d}'
        if p.kind == 'circle' and p.center is not None:
            result.append((np.array([p.center.x, p.center.y]), label + ':centre'))
            for x, y, suffix in [(p.radius, 0, 'right'), (-p.radius, 0, 'left'), (0, p.radius, 'top'), (0, -p.radius, 'bottom')]:
                result.append((np.array([p.center.x+x, p.center.y+y]), label+':'+suffix))
        elif p.points:
            for q, suffix in [(p.points[0], 'start'), (p.points[-1], 'end')]:
                result.append((np.array([q.x, q.y]), label+':'+suffix))
    # A shared vertex of adjacent edges is a single location, not an ambiguity.
    unique = {}
    for point, label in result:
        key = tuple(np.round(point, 7))
        if key in unique:
            unique[key] = (point, unique[key][1] + '/' + label)
        else: unique[key] = (point, label)
    return tuple(unique.values())


def associate(point, features, radius):
    ranked = sorted((float(np.linalg.norm(p-point)), label, p) for p, label in features)
    if not ranked or ranked[0][0] > radius:
        raise ValueError('No projected vertex or centre at the dimension anchor.')
    if len(ranked) > 1 and ranked[1][0] - ranked[0][0] <= 1e-6:
        raise ValueError('Ambiguous projected features at the dimension anchor.')
    return ranked[0][2], ranked[0][1]


def point(v): return np.array([float(v.x), float(v.y)])


def circular_anchor_on_sweep(primitive, anchor):
    if primitive.kind == 'circle': return True
    if primitive.kind != 'arc' or primitive.center is None: return False
    centre=np.array([primitive.center.x,primitive.center.y])
    angles=np.unwrap([math.atan2(q.y-centre[1],q.x-centre[0]) for q in primitive.points])
    angle=math.atan2(anchor[1]-centre[1],anchor[0]-centre[0])
    low,high=min(angles),max(angles)
    return any(low-1e-7 <= angle+shift*2*math.pi <= high+1e-7 for shift in range(-2,3))


def circular_features(primitives):
    """Join analytic arcs only when their angular union proves a full circle."""
    from app.projection import ProjectedPrimitive
    groups={}
    for p in primitives:
        if p.kind not in {'circle','arc'} or p.center is None or p.radius is None:continue
        key=(round(p.center.x,7),round(p.center.y,7),round(p.radius,7))
        groups.setdefault(key,[]).append(p)
    result=[]
    tau=2*math.pi
    for group in groups.values():
        if any(p.kind=='circle' for p in group):
            result.append(next(p for p in group if p.kind=='circle'));continue
        intervals=[]
        for p in group:
            angles=np.unwrap([math.atan2(q.y-p.center.y,q.x-p.center.x) for q in p.points])
            if len(angles)<2:continue
            lo,hi=float(min(angles)),float(max(angles));length=hi-lo;lo%=tau;hi=lo+length
            intervals.append((lo,min(hi,tau)))
            if hi>tau:intervals.append((0,hi-tau))
        merged=[]
        for lo,hi in sorted(intervals):
            if merged and lo<=merged[-1][1]+1e-7:merged[-1]=(merged[-1][0],max(hi,merged[-1][1]))
            else:merged.append((lo,hi))
        if merged and merged[0][0]<1e-7 and merged[-1][1]>tau-1e-7 and sum(b-a for a,b in merged)>tau-1e-7:
            p=group[0];points=tuple(Point2D(p.center.x+p.radius*math.cos(t),p.center.y+p.radius*math.sin(t)) for t in np.linspace(0,tau,97))
            result.append(ProjectedPrimitive('circle',points,p.center,p.radius))
        else:result.extend(group)
    return tuple(result)


def linear_diameter_target(entity,drawing):
    """A linear Ø callout is valid only with opposite anchors on a drawn circle."""
    if not entity.dxf.hasattr('defpoint2') or not entity.dxf.hasattr('defpoint3'):return None
    a,b=point(entity.dxf.defpoint2),point(entity.dxf.defpoint3);centre=(a+b)/2
    targets=[p for p in circular_features(drawing) if p.kind=='circle'
             and np.linalg.norm(centre-[p.center.x,p.center.y])<1e-4
             and abs(np.linalg.norm(b-a)-2*p.radius)<1e-4]
    return targets[0] if len(targets)==1 else None


def simple_profile_roles(primitives):
    """Prove a simple profile's topology, then name its geometric roles.

    This is deliberately limited to concentric circles, axis-aligned rectangles
    and capsules. No nominal text, search radius or resized model is involved.
    Complex or changed topology must use the ordinary spatial association.
    """
    primitives=unique_primitives(tuple(p for p in primitives if p.kind not in {'circle','arc'})+circular_features(primitives))
    if not primitives:return None
    circles=[p for p in primitives if p.kind=='circle']
    if len(circles)==len(primitives):
        centre=point(circles[0].center)
        if any(np.linalg.norm(point(p.center)-centre)>1e-7 for p in circles):return None
        ordered=sorted(circles,key=lambda p:p.radius)
        return ('concentric',len(ordered)),{},tuple(ordered)
    lines=[p for p in primitives if p.kind=='line' and len(p.points)>=2]
    arcs=[p for p in primitives if p.kind=='arc' and p.center is not None and p.radius is not None]
    if len(lines)+len(arcs)!=len(primitives):return None
    lo,hi=bounds(primitives)
    if np.any(hi-lo<1e-7):return None
    endpoints=[point(q) for p in primitives for q in (p.points[0],p.points[-1])]
    # Every endpoint must join exactly one other edge endpoint.
    if any(sum(np.linalg.norm(q-r)<1e-7 for r in endpoints)!=2 for q in endpoints):return None
    if len(lines)==4 and not arcs:
        if any(min(abs((point(p.points[-1])-point(p.points[0]))))>1e-7 for p in lines):return None
        if any(not all(min(abs(q[i]-lo[i]),abs(q[i]-hi[i]))<1e-7 for i in (0,1)) for q in endpoints):return None
        signature=('rectangle',)
    elif len(lines)==2 and len(arcs)==2:
        a,b=arcs
        if abs(a.radius-b.radius)>1e-7 or a.radius<=0:return None
        delta=point(b.center)-point(a.center)
        if np.linalg.norm(delta)<1e-7 or min(abs(delta))>1e-7:return None
        axis=int(np.argmax(abs(delta)))
        for arc in arcs:
            angles=np.unwrap([math.atan2(q.y-arc.center.y,q.x-arc.center.x) for q in arc.points])
            if abs(float(max(angles)-min(angles))-math.pi)>1e-6:return None
            for q in (arc.points[0],arc.points[-1]):
                v=point(q)-point(arc.center)
                if abs(v[axis])>1e-7 or abs(abs(v[1-axis])-arc.radius)>1e-7:return None
        if any(abs((point(p.points[-1])-point(p.points[0]))[1-axis])>1e-7 for p in lines):return None
        # The caps must point away from each other, forming an outer capsule.
        for arc,other in ((a,b),(b,a)):
            middle=point(arc.points[len(arc.points)//2])-point(arc.center)
            if np.dot(middle,point(other.center)-point(arc.center))>=0:return None
        signature=('capsule',axis)
    else:return None
    features=landmarks(primitives)
    coordinates=[sorted(set(round(float(q[i]),7) for q,_ in features)) for i in (0,1)]
    roles={}
    for q,label in features:
        role=tuple(coordinates[i].index(round(float(q[i]),7)) for i in (0,1))
        roles[role]=(q,label+':topology')
    return signature,roles,tuple(sorted(arcs,key=lambda p:float(point(p.center)[signature[1]]))) if arcs else (signature,roles,())


def profile_correspondence(drawing,projected):
    a,b=simple_profile_roles(drawing),simple_profile_roles(projected)
    if a is None or b is None or a[0]!=b[0] or set(a[1])!=set(b[1]):return None
    return a,b


def measure_dimension(entity, projected, drawing, association_mm, linear_diameter=False):
    """Measure spatially selected geometry, never nearest nominal size."""
    code = int(entity.dxf.dimtype) & 15
    if code in (0, 1) and not linear_diameter:
        if not entity.dxf.hasattr('defpoint2') or not entity.dxf.hasattr('defpoint3'):
            raise ValueError('Dimension extension-line origins are missing.')
        a, b = point(entity.dxf.defpoint2), point(entity.dxf.defpoint3)
        # Require anchors to refer to geometry in this DXF view as well.
        for q in (a, b): associate(q, landmarks(drawing), 1e-4)
        correspondence=profile_correspondence(drawing,projected)
        if correspondence is not None and correspondence[0][1]:
            source,destination=correspondence
            def match(q):
                roles=[role for role,(p,_) in source[1].items() if np.linalg.norm(q-p)<1e-4]
                if len(roles)!=1:raise ValueError('Dimension anchor has no unique topological role.')
                return destination[1][roles[0]]
            pa,la=match(a);pb,lb=match(b)
        else:
            pa, la = associate(a, landmarks(projected), association_mm)
            pb, lb = associate(b, landmarks(projected), association_mm)
        if np.linalg.norm(pa-pb) < 1e-7:
            raise ValueError('Both dimension anchors mapped to the same model location.')
        if code == 1: value = float(np.linalg.norm(pb-pa))
        else:
            angle = math.radians(float(entity.dxf.get('angle', 0)))
            value = abs(float(np.dot(pb-pa, [math.cos(angle), math.sin(angle)])))
        return value, (la, lb), (tuple(pa), tuple(pb))
    if code in (3, 4) or linear_diameter:
        if not linear_diameter and not entity.dxf.hasattr('defpoint4'):
            raise ValueError('Circular dimension reference points are missing.')
        if linear_diameter:
            a,b=point(entity.dxf.defpoint2),point(entity.dxf.defpoint3);code=3
        else:a, b = point(entity.dxf.defpoint), point(entity.dxf.defpoint4)
        centre = (a+b)/2 if code == 3 else a
        # Select the DXF circle by centre AND the actual radial anchor, not its text.
        candidates = [p for p in circular_features(drawing) if p.center is not None and p.radius is not None
                      and np.linalg.norm(centre - [p.center.x, p.center.y]) < 1e-4
                      and abs(np.linalg.norm(b-centre)-p.radius) < 1e-4
                      and (p.kind=='circle' if code==3 else circular_anchor_on_sweep(p,b))]
        if len(candidates) != 1:
            raise ValueError('Circular dimension does not identify one drawn circle/arc.')
        target = candidates[0]
        correspondence=profile_correspondence(drawing,projected)
        if correspondence is not None:
            source,destination=correspondence
            roles=[i for i,p in enumerate(source[2]) if p is target]
            # circular_features creates new objects for joined semicircles.
            if not roles:
                roles=[i for i,p in enumerate(source[2]) if p.kind==target.kind and abs(p.radius-target.radius)<1e-7
                       and np.linalg.norm(point(p.center)-point(target.center))<1e-7]
            if len(roles)==1:
                i=roles[0];p=destination[2][i]
                return p.radius*(2 if code==3 else 1),(f'PROFILE:{source[0][0]}:circle-{i+1}:topology',),((p.center.x,p.center.y),)
        candidates = [(i, p) for i, p in enumerate(circular_features(projected), 1)
                      if (p.kind=='circle' or code==4 and p.kind=='arc') and p.center is not None and p.radius is not None
                      and np.linalg.norm(centre-[p.center.x,p.center.y]) <= association_mm
                      and abs(target.radius-p.radius) <= association_mm
                      and circular_anchor_on_sweep(p,np.array([p.center.x,p.center.y])+(b-centre)*p.radius/target.radius)]
        if len(candidates) != 1:
            raise ValueError('Circular anchor has no unique corresponding projected circle. Select a face-on view or section.')
        i, p = candidates[0]
        return p.radius * (2 if code == 3 else 1), (f'EDGE-{i:03d}:{p.kind}',), ((p.center.x, p.center.y),)
    raise ValueError('This dimension type is not supported by the initial geometry checker.')


def check_dimension(entity, dimension_id, view, projection, drawing, association_mm=1., general_tolerance=None, confirmed=False, comparison_mode='limits'):
    code = int(entity.dxf.dimtype) & 15
    kind = {0:'linear', 1:'aligned', 3:'diameter', 4:'radius'}.get(code, 'unsupported')
    raw = str(entity.dxf.get('text', '<>'))
    try: geometric_measure = float(entity.get_measurement())
    except (ValueError, TypeError, AttributeError): geometric_measure = None
    text_error = None
    effective_raw=raw
    style=entity.override()
    try:
        if geometric_measure is not None and ('<>' in raw or not raw):
            from ezdxf.render.dim_base import format_text
            rounding=float(style.get('dimrnd',0))
            if not math.isfinite(rounding) or rounding<0: raise ValueError('Invalid DXF rounding increment.')
            displayed=format_text(geometric_measure,dimrnd=rounding or None,dimdec=int(style.get('dimdec',2)))
            post=str(style.get('dimpost','') or '')
            if post:
                if post.count('<>')!=1: raise ValueError('Unsupported DXF dimension prefix/suffix format.')
                displayed=post.replace('<>',displayed,1)
            effective_raw=raw.replace('<>',displayed,1) if raw else displayed
        parsed = parse_checked_dimension_text(effective_raw, geometric_measure)
    except (ValueError,OverflowError) as exc:
        parsed=ParsedDimensionText(None,None); text_error=str(exc)
    tolerance, source = parsed.tolerance, 'Explicit drawing tolerance'
    # Native DXF tolerance overrides take precedence over the optional project limit.
    if tolerance is None:
        style = entity.override()
        if style.get('dimtol', 0) or style.get('dimlim', 0):
            from app.drawing_interpreter import Tolerance
            tolerance = Tolerance(-float(style.get('dimtm', 0)), float(style.get('dimtp', 0)))
            source = 'DXF dimension style'
    if tolerance is None and general_tolerance is not None:
        from app.drawing_interpreter import Tolerance
        tolerance = Tolerance(-general_tolerance, general_tolerance); source = 'User-enabled project tolerance'
    lower = parsed.nominal_value+tolerance.lower_deviation if tolerance and parsed.nominal_value is not None else None
    upper = parsed.nominal_value+tolerance.upper_deviation if tolerance and parsed.nominal_value is not None else None
    nominal_result=tolerance_result='Not checked'
    def row(measured, result, reason, features=(), anchors=()):
        return DimensionCheck(dimension_id, view, kind, parsed.nominal_value, measured, lower, upper,
                              result, reason, features, anchors, source if tolerance else 'Unavailable',nominal_result,tolerance_result)
    if text_error:
        return row(None,'NG','Cannot verify: '+text_error)
    style=entity.override()
    if style.get('dimalt',0) or int(style.get('dimlunit',2))!=2:
        return row(None,'NG','Cannot verify: dual-unit or non-decimal dimension formatting is not supported.')
    prefix=_normalize_text(effective_raw).upper().lstrip()
    linear_diameter=prefix.startswith(('⌀','Ø')) and code in (0,1) and linear_diameter_target(entity,drawing) is not None
    if linear_diameter:kind='diameter'
    if (prefix.startswith(('⌀','Ø')) and code!=3 and not linear_diameter) or (prefix.startswith('R') and code!=4):
        return row(None,'NG','Cannot verify: radius/diameter symbol conflicts with native dimension type.')
    if not math.isclose(float(style.get('dimlfac',1)),1.,rel_tol=0,abs_tol=1e-12):
        return row(None,'NG','Cannot verify: scaled DXF dimension (DIMLFAC) requires an explicit drawing scale.')
    if not np.allclose(tuple(entity.dxf.get('extrusion',(0,0,1))),(0,0,1),rtol=0,atol=1e-9):
        return row(None,'NG','Cannot verify: dimension is not in the supported XY drawing plane.')
    anchor_names=('defpoint2','defpoint3') if code in (0,1) else ('defpoint','defpoint4') if code in (3,4) else ()
    anchor_z=[float(entity.dxf.get(name).z) for name in anchor_names if entity.dxf.hasattr(name)]
    if anchor_z and max(anchor_z)-min(anchor_z)>1e-7:
        return row(None,'NG','Cannot verify: dimension anchors are not in one XY plane.')
    if any(v is not None and not math.isfinite(v) for v in (parsed.nominal_value,lower,upper)) or (lower is not None and upper is not None and lower>upper):
        parsed=ParsedDimensionText(parsed.nominal_value if parsed.nominal_value is not None and math.isfinite(parsed.nominal_value) else None,None)
        lower=upper=None; tolerance=None
        return row(None,'NG','Cannot verify: invalid numeric dimension or tolerance limits.')
    if parsed.nominal_value is None:
        return row(None, 'NG', 'Cannot verify: dimension has no numeric nominal value.')
    if raw == ' ' or any(t in raw.upper() for t in ('REF', 'TYP', 'X', '×')):
        return row(None, 'NG', 'Cannot verify: reference/quantity callout requires explicit feature scope.')
    if '\\' in _normalize_text(raw):
        return row(None, 'NG', 'Cannot verify: unsupported formatted dimension text.')
    try:
        measured, features, anchors = measure_dimension(entity, projection.primitives, drawing, association_mm,linear_diameter)
    except ValueError as exc:
        return row(None, 'NG', f'Cannot verify: {exc}')
    if not confirmed:
        return row(measured,'NG','Cannot verify: confirm the selected view/section, alignment and drawing units. Measurement shown is preliminary.',features,anchors)
    nominal_result='Match' if abs(measured-parsed.nominal_value)<=1e-6 else 'Mismatch'
    tolerance_result='Not specified' if lower is None or upper is None else 'Within limits' if lower-1e-8<=measured<=upper+1e-8 else 'Outside limits'
    if comparison_mode=='nominal':
        return row(measured,'OK' if nominal_result=='Match' else 'NG','Nominal dimensions match (numerical precision 0.000001 mm); tolerance acceptance is separate.' if nominal_result=='Match' else 'Measured geometry differs from the drawing nominal.',features,anchors)
    if comparison_mode!='limits':return row(measured,'NG','Cannot verify: invalid comparison mode.',features,anchors)
    if lower is None or upper is None:
        return row(measured, 'NG', 'Cannot verify: no explicit or enabled project tolerance.', features, anchors)
    passed = lower-1e-8 <= measured <= upper+1e-8
    return row(measured, 'OK' if passed else 'NG', 'Within dimension limits.' if passed else 'Measured geometry is outside dimension limits.', features, anchors)


def overall_result(checks):
    return 'OK' if checks and all(c.result == 'OK' for c in checks) else 'NG'


def unresolved_dimension(entity,dimension_id,reason):
    """Retain the drawing nominal even if its view could not be measured."""
    empty=StepProjection('Unassigned',0,0,())
    row=check_dimension(entity,dimension_id,'Unassigned',empty,(),confirmed=False)
    return replace(row,measured=None,reason='Cannot verify: '+reason,features=(),anchors=())


def suggest_projection(shape,drawing,cache):
    """Suggest from actual outline size/circles; operator still confirms the view."""
    lo,hi=bounds(drawing);w,h=np.maximum(hi-lo,1e-9)
    count=sum(p.kind=='circle' for p in circular_features(drawing))
    ranked=[]
    for index,name in enumerate(('top','front','right','bottom','rear','left')):
        key=('Projection',name,False)
        if key not in cache:cache[key]=project_visible(shape,name)
        p=cache[key];cw,ch=max(p.width,1e-9),max(p.height,1e-9)
        nc=sum(q.kind=='circle' for q in circular_features(p.primitives))
        score=abs(math.log(cw/w))+abs(math.log(ch/h))+.25*abs(nc-count)
        ranked.append((score,index,name))
    return min(ranked)[2]


def svg_overlay(drawing, projection, checks=()):
    """Exact coordinate SVG for in-app evidence, not a generative illustration."""
    all_primitives = tuple(drawing) + tuple(projection.primitives)
    low, high = bounds(all_primitives); width, height = np.maximum(high-low, .1)
    margin = max(width,height)*.06
    stroke = max(width,height)/600
    chunks = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{low[0]-margin} {-high[1]-margin} {width+2*margin} {height+2*margin}" width="100%" height="380" style="background:#fafafa">']
    for primitives, colour in [(drawing,'#334155'), (projection.primitives,'#c47b26')]:
        for p in primitives:
            points = ' '.join(f'{q.x},{-q.y}' for q in p.points)
            if p.kind == 'circle' and p.center is not None:
                chunks.append(f'<circle cx="{p.center.x}" cy="{-p.center.y}" r="{p.radius}" fill="none" stroke="{colour}" stroke-width="{stroke}"/>')
            else:
                chunks.append(f'<polyline points="{points}" fill="none" stroke="{colour}" stroke-width="{stroke}"/>')
    for check in checks:
        colour = '#16814a' if check.result == 'OK' else '#c62828'
        for x,y in check.anchors:
            chunks.append(f'<circle cx="{x}" cy="{-y}" r="{stroke*3}" fill="{colour}"/>')
    return ''.join(chunks)+'</svg>'
