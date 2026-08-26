"""Deterministically split model-space DXF entities into independent view regions."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from app.dxf_reader import DxfAnalysis, EntityLocation, Point2D

@dataclass(frozen=True)
class DrawingView:
    view_id: str
    entity_indexes: tuple[int, ...]
    minimum: Point2D
    maximum: Point2D
    dimension_indexes: tuple[int, ...]
    geometry_count: int
    evidence: tuple[str, ...] = ()
    def to_dict(self) -> dict[str, object]: return asdict(self)

def _gap(a: EntityLocation, b: EntityLocation) -> float:
    return max(0.0, max(b.minimum.x-a.maximum.x, a.minimum.x-b.maximum.x, b.minimum.y-a.maximum.y, a.minimum.y-b.maximum.y))

def segment_views(analysis: DxfAnalysis, gap_mm: float = 12.0) -> tuple[DrawingView, ...]:
    """Cluster nearby geometry; annotations are assigned only after geometry is isolated."""
    annotations = {"DIMENSION", "TEXT", "MTEXT"}
    geometric = [item for item in analysis.entity_locations if item.entity_type not in annotations]
    if not geometric: return ()
    clusters: list[list[EntityLocation]] = []
    for item in geometric:
        close = [c for c in clusters if any(_gap(item, member) <= gap_mm for member in c)]
        if not close: clusters.append([item]); continue
        target = close[0]; target.append(item)
        for extra in close[1:]: target.extend(extra); clusters.remove(extra)
    views: list[DrawingView] = []
    for number, cluster in enumerate(sorted(clusters, key=lambda c: min(x.minimum.x for x in c)), 1):
        minimum = Point2D(min(x.minimum.x for x in cluster), min(x.minimum.y for x in cluster))
        maximum = Point2D(max(x.maximum.x for x in cluster), max(x.maximum.y for x in cluster))
        entity_indexes = {x.entity_index for x in cluster}
        dimensions = []
        for dimension in analysis.dimensions:
            point = dimension.text_position or dimension.definition_point
            if point and minimum.x-gap_mm <= point.x <= maximum.x+gap_mm and minimum.y-gap_mm <= point.y <= maximum.y+gap_mm:
                dimensions.append(dimension.entity_index); entity_indexes.add(dimension.entity_index)
        views.append(DrawingView(f"VIEW-{number:02d}", tuple(sorted(entity_indexes)), minimum, maximum, tuple(dimensions), len(cluster)))
    return tuple(views)

def assign_dimension_view(analysis: DxfAnalysis, views: tuple[DrawingView, ...], entity_index: int) -> str | None:
    matches = [view.view_id for view in views if entity_index in view.dimension_indexes]
    return matches[0] if len(matches) == 1 else None
