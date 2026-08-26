"""Generate deterministic centre-plane STEP section candidates."""
from __future__ import annotations
from dataclasses import dataclass
from app.projection import StepProjection, project_step_bytes

@dataclass(frozen=True)
class StepSection:
    plane: str; projection: StepProjection

def generate_step_sections(data: bytes, filename: str) -> tuple[StepSection, ...]:
    """Centre-plane candidates use the corresponding orthographic edge projection.

    Offset and non-orthogonal cuts are intentionally not inferred in Milestone 13.
    """
    names = {"top": "Z-centre section", "front": "Y-centre section", "right": "X-centre section"}
    return tuple(StepSection(names[p.view], p) for p in project_step_bytes(data, filename))
