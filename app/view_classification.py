"""Evidence-based standard, section, and detail view classification."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import re
from app.dxf_reader import DxfAnalysis
from app.view_segmentation import DrawingView

@dataclass(frozen=True)
class ViewClassification:
    view_id: str; detected_type: str; evidence: tuple[str, ...]; confidence: str
    def to_dict(self) -> dict[str, object]: return asdict(self)

SECTION = re.compile(r"(?:SECTION\s+)?[A-Z]\s*[-–]\s*[A-Z]", re.I)
DETAIL = re.compile(r"\bDETAIL\b", re.I)
def classify_view(analysis: DxfAnalysis, view: DrawingView) -> ViewClassification:
    evidence=[]
    nearby = [text.content for text in analysis.texts if text.position and view.minimum.x-20 <= text.position.x <= view.maximum.x+20 and view.minimum.y-20 <= text.position.y <= view.maximum.y+20]
    if any(SECTION.search(text) for text in nearby): evidence.append("Section label detected")
    if analysis.hatch_count and any(x.entity_index in view.entity_indexes and x.entity_type == "HATCH" for x in analysis.entity_locations): evidence.append("HATCH entities detected")
    if len(evidence) >= 2: return ViewClassification(view.view_id, "Full section", tuple(evidence), "High")
    if any(DETAIL.search(text) for text in nearby): return ViewClassification(view.view_id, "Detail view", ("Detail label detected",), "Medium")
    return ViewClassification(view.view_id, "Unknown view", tuple(evidence) or ("No unambiguous view label",), "Low")

def classify_views(analysis: DxfAnalysis, views: tuple[DrawingView, ...]) -> tuple[ViewClassification, ...]: return tuple(classify_view(analysis, view) for view in views)
