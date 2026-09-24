"""Actual plane/solid intersections, not renamed orthographic projections."""
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
import cadquery as cq
from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
from OCP.gp import gp_Pln, gp_Pnt, gp_Dir
from app.projection import StepProjection, ProjectionError, project_step_shape

@dataclass(frozen=True)
class StepSection:
    plane: str
    projection: StepProjection

def section_shape(shape: cq.Shape, axis: str, offset: float) -> StepProjection:
    """Cut at an absolute STEP coordinate in millimetres."""
    axis = axis.upper()
    if axis not in {'X', 'Y', 'Z'}:
        raise ProjectionError('Section axis must be X, Y, or Z.')
    index = 'XYZ'.index(axis)
    point, normal = [0., 0., 0.], [0., 0., 0.]
    point[index], normal[index] = float(offset), 1.
    op = BRepAlgoAPI_Section(shape.wrapped, gp_Pln(gp_Pnt(*point), gp_Dir(*normal)), False)
    op.ComputePCurveOn1(True)
    op.Approximation(True)
    op.Build()
    if not op.IsDone() or op.Shape().IsNull():
        raise ProjectionError('The selected plane has no usable STEP intersection.')
    cut = cq.Shape.cast(op.Shape())
    if not cut.Edges():
        raise ProjectionError('The selected plane does not cut the solid.')
    return project_step_shape(cut, {'X': 'right', 'Y': 'front', 'Z': 'top'}[axis])

def generate_step_sections(data: bytes, filename: str) -> tuple[StepSection, ...]:
    if Path(filename).suffix.lower() not in {'.stp', '.step'} or not data:
        raise ProjectionError('A nonempty STEP/STP file is required.')
    with NamedTemporaryFile(suffix='.step') as temporary:
        temporary.write(data)
        temporary.flush()
        shape = cq.importers.importStep(temporary.name).val()
    b = shape.BoundingBox()
    return tuple(StepSection(f'{axis}-centre section', section_shape(shape, axis, value))
                 for axis, value in zip('XYZ', ((b.xmin+b.xmax)/2, (b.ymin+b.ymax)/2, (b.zmin+b.zmax)/2)))
