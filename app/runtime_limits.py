"""Validated, versioned pilot runtime limits with no operator-editable values."""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


class RuntimeLimitsError(ValueError):
    """Raised when a runtime-limits configuration is unsafe or incomplete."""


@dataclass(frozen=True)
class RuntimeLimits:
    version: str
    max_dxf_bytes: int
    max_step_bytes: int
    max_dxf_entities: int
    max_step_faces: int
    max_step_edges: int
    cad_processing_timeout_seconds: int
    ai_request_timeout_seconds: int
    max_report_requests_per_run: int


def _default_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "runtime_limits.json"


def validate_runtime_limits(payload: dict[str, object]) -> RuntimeLimits:
    required = ("version", "max_dxf_bytes", "max_step_bytes", "max_dxf_entities", "max_step_faces", "max_step_edges", "cad_processing_timeout_seconds", "ai_request_timeout_seconds", "max_report_requests_per_run")
    if any(key not in payload for key in required):
        raise RuntimeLimitsError("Runtime-limit configuration is missing required fields.")
    if not isinstance(payload["version"], str) or not payload["version"]:
        raise RuntimeLimitsError("Runtime-limit version must be a non-empty string.")
    values = {key: payload[key] for key in required[1:]}
    if any(not isinstance(value, int) or value <= 0 for value in values.values()):
        raise RuntimeLimitsError("All runtime limits must be positive integers.")
    return RuntimeLimits(str(payload["version"]), **values)  # type: ignore[arg-type]


@lru_cache(maxsize=1)
def load_runtime_limits(path: str | Path | None = None) -> RuntimeLimits:
    """Load the committed pilot configuration once per process."""
    target = Path(path) if path is not None else _default_path()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeLimitsError(f"Unable to load runtime limits: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeLimitsError("Runtime-limit configuration root must be an object.")
    return validate_runtime_limits(payload)
