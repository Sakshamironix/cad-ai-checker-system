"""Offline health checks for the container and pilot runtime."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from tempfile import TemporaryDirectory

from app.runtime_limits import load_runtime_limits
from app.tolerance_validation import load_validated_tolerance_rules

APP_VERSION = "CAD AI Checker v0.16.0-pilot"


@dataclass(frozen=True)
class HealthStatus:
    healthy: bool
    checks: dict[str, bool]
    version: str

    def to_dict(self) -> dict[str, object]: return asdict(self)


def check_health() -> HealthStatus:
    checks: dict[str, bool] = {}
    try:
        import cadquery, ezdxf, reportlab, streamlit  # noqa: F401
        checks["libraries"] = True
    except ImportError:
        checks["libraries"] = False
    try:
        load_runtime_limits(); load_validated_tolerance_rules("config/general_tolerances.json")
        checks["configuration"] = True
    except ValueError:
        checks["configuration"] = False
    try:
        with TemporaryDirectory() as directory:
            path = __import__("pathlib").Path(directory) / "health.tmp"; path.write_text("ok"); checks["temporary_storage"] = path.read_text() == "ok"
    except OSError:
        checks["temporary_storage"] = False
    return HealthStatus(all(checks.values()), checks, APP_VERSION)
