from __future__ import annotations

import pytest

from app.runtime_limits import RuntimeLimitsError, load_runtime_limits, validate_runtime_limits


def test_committed_runtime_limits_are_valid() -> None:
    limits = load_runtime_limits()
    assert limits.max_dxf_bytes == 25 * 1024 * 1024
    assert limits.cad_processing_timeout_seconds == 120


def test_rejects_non_positive_runtime_limit() -> None:
    with pytest.raises(RuntimeLimitsError, match="positive integers"):
        validate_runtime_limits({"version":"1", "max_dxf_bytes":0, "max_step_bytes":1, "max_dxf_entities":1, "max_step_faces":1, "max_step_edges":1, "cad_processing_timeout_seconds":1, "ai_request_timeout_seconds":1, "max_report_requests_per_run":1})
