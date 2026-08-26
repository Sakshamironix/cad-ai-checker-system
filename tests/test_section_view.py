from app.section_view import interpret_section
from app.view_classification import ViewClassification

def test_full_section_evidence_is_preserved() -> None:
    result=interpret_section(ViewClassification("SECTION-01", "Full section", ("HATCH entities detected", "Section label detected"), "High"))
    assert result.is_section and result.section_kind == "Full section"
