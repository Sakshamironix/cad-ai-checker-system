from __future__ import annotations

import pytest

from app.reporting import FinalReport, validate_report_payload


def _payload() -> dict[str, object]:
    return FinalReport("2026-01-01T00:00:00+00:00", "OK", "OK", "valid", "drawing.dxf", "model.step", True, (), (), (), None, (), (), None, (), ()).to_dict()


def test_generated_json_report_satisfies_pilot_validation() -> None:
    validate_report_payload(_payload())


def test_report_validation_rejects_non_finite_values() -> None:
    payload = _payload()
    payload["dimension_summary"] = [{"drawing_mm": float("nan")}]
    with pytest.raises(ValueError, match="non-finite"):
        validate_report_payload(payload)
