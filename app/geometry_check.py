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
from app.drawing_interpreter import parse_dimension_text
from app.runtime_limits import load_runtime_limits

ENGINE_VERSION = '0.18.0-geometry'

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
        shape = cq.importers.importStep(f.name).val()
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
    analytic_circles = []
    yaxis = np.cross(normal, xaxis)
    for face in shape.Faces():
        surface = BRepAdaptor_Surface(face.wrapped)
        if surface.GetType() != GeomAbs_Torus:
            continue
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
    return replace(p, view=view, primitives=tuple(normalized))


def bounds(primitives):
    points = np.array([(p.x, p.y) for item in primitives for p in item.points])
    if not len(points):
        raise ValueError('No drawing geometry selected. Check layer and view filters.')
    return points.min(axis=0), points.max(axis=0)


def drawing_primitives(doc, indexes, excluded_layers=()):
    return tuple(p for i, e in enumerate(doc.modelspace(), 1)
                 if i in indexes and e.dxf.layer not in excluded_layers
                 for p in _entity_primitives(e))


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
    return replace(projection, primitives=tuple(replace(p, points=tuple(move(q) for q in p.points),
                   center=move(p.center) if p.center else None) for p in rotated))


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


def measure_dimension(entity, projected, drawing, association_mm):
    """Measure spatially selected geometry, never nearest nominal size."""
    code = int(entity.dxf.dimtype) & 15
    if code in (0, 1):
        if not entity.dxf.hasattr('defpoint2') or not entity.dxf.hasattr('defpoint3'):
            raise ValueError('Dimension extension-line origins are missing.')
        a, b = point(entity.dxf.defpoint2), point(entity.dxf.defpoint3)
        # Require anchors to refer to geometry in this DXF view as well.
        for q in (a, b): associate(q, landmarks(drawing), 1e-4)
        pa, la = associate(a, landmarks(projected), association_mm)
        pb, lb = associate(b, landmarks(projected), association_mm)
        if np.linalg.norm(pa-pb) < 1e-7:
            raise ValueError('Both dimension anchors mapped to the same model location.')
        if code == 1: value = float(np.linalg.norm(pb-pa))
        else:
            angle = math.radians(float(entity.dxf.get('angle', 0)))
            value = abs(float(np.dot(pb-pa, [math.cos(angle), math.sin(angle)])))
        return value, (la, lb), (tuple(pa), tuple(pb))
    if code in (3, 4):
        if not entity.dxf.hasattr('defpoint4'):
            raise ValueError('Circular dimension reference points are missing.')
        a, b = point(entity.dxf.defpoint), point(entity.dxf.defpoint4)
        centre = (a+b)/2 if code == 3 else a
        # Select the DXF circle by centre AND the actual radial anchor, not its text.
        candidates = [p for p in drawing if p.center is not None and p.radius is not None
                      and np.linalg.norm(centre - [p.center.x, p.center.y]) < 1e-4
                      and abs(np.linalg.norm(b-centre)-p.radius) < 1e-4]
        if len(candidates) != 1:
            raise ValueError('Circular dimension does not identify one drawn circle/arc.')
        target = candidates[0]
        candidates = [(i, p) for i, p in enumerate(projected, 1)
                      if p.kind == 'circle' and p.center is not None and p.radius is not None
                      and np.linalg.norm(centre-[p.center.x,p.center.y]) <= association_mm
                      and abs(target.radius-p.radius) <= association_mm]
        if len(candidates) != 1:
            raise ValueError('Circular anchor has no unique corresponding projected circle. Select a face-on view or section.')
        i, p = candidates[0]
        return p.radius * (2 if code == 3 else 1), (f'EDGE-{i:03d}:circle',), ((p.center.x, p.center.y),)
    raise ValueError('This dimension type is not supported by the initial geometry checker.')


def check_dimension(entity, dimension_id, view, projection, drawing, association_mm=1., general_tolerance=None, confirmed=False):
    code = int(entity.dxf.dimtype) & 15
    kind = {0:'linear', 1:'aligned', 3:'diameter', 4:'radius'}.get(code, 'unsupported')
    raw = str(entity.dxf.get('text', '<>'))
    try: geometric_measure = float(entity.get_measurement())
    except (ValueError, TypeError, AttributeError): geometric_measure = None
    parsed = parse_dimension_text(raw, geometric_measure)
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
    def row(measured, result, reason, features=(), anchors=()):
        return DimensionCheck(dimension_id, view, kind, parsed.nominal_value, measured, lower, upper,
                              result, reason, features, anchors, source if tolerance else 'Unavailable')
    if not confirmed:
        return row(None, 'NG', 'Cannot verify: confirm the selected view/section and alignment.')
    if parsed.nominal_value is None:
        return row(None, 'NG', 'Cannot verify: dimension has no numeric nominal value.')
    if raw == ' ' or any(t in raw.upper() for t in ('REF', 'TYP', 'X', '×')):
        return row(None, 'NG', 'Cannot verify: reference/quantity callout requires explicit feature scope.')
    if '\\' in raw.replace('\\U+2205','').replace('\\u+2205',''):
        return row(None, 'NG', 'Cannot verify: unsupported formatted dimension text.')
    try:
        measured, features, anchors = measure_dimension(entity, projection.primitives, drawing, association_mm)
    except ValueError as exc:
        return row(None, 'NG', f'Cannot verify: {exc}')
    if lower is None or upper is None:
        return row(measured, 'NG', 'Cannot verify: no explicit or enabled project tolerance.', features, anchors)
    passed = lower-1e-8 <= measured <= upper+1e-8
    return row(measured, 'OK' if passed else 'NG', 'Within dimension limits.' if passed else 'Measured geometry is outside dimension limits.', features, anchors)


def overall_result(checks):
    return 'OK' if checks and all(c.result == 'OK' for c in checks) else 'NG'


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
