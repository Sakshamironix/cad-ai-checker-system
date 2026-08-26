"""Safe performance diagnostics. CAD contents and credentials are never recorded."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from time import perf_counter


@dataclass(frozen=True)
class TimingRecord:
    stage: str
    duration_seconds: float


@dataclass
class RunDiagnostics:
    application_version: str
    records: list[TimingRecord] = field(default_factory=list)

    @contextmanager
    def measure(self, stage: str):
        started = perf_counter()
        try:
            yield
        finally:
            self.records.append(TimingRecord(stage, perf_counter() - started))

    @property
    def total_seconds(self) -> float:
        return sum(record.duration_seconds for record in self.records)

    def to_dict(self) -> dict[str, object]:
        return {"application_version": self.application_version, "stages": [asdict(record) for record in self.records], "total_seconds": self.total_seconds}
