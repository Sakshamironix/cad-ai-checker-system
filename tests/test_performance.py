from __future__ import annotations

from app.diagnostics import RunDiagnostics


def test_diagnostics_preserve_stage_order_and_total() -> None:
    diagnostics = RunDiagnostics("CAD AI Checker v0.16.0-pilot")
    with diagnostics.measure("DXF parsing"):
        pass
    with diagnostics.measure("Feature mapping"):
        pass
    payload = diagnostics.to_dict()
    assert [stage["stage"] for stage in payload["stages"]] == ["DXF parsing", "Feature mapping"]
    assert payload["total_seconds"] >= 0
