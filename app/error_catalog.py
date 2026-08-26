"""Controlled bilingual errors exposed by the pilot dashboard."""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ControlledError:
    error_id: str
    category: str
    stage: str
    message_en: str
    message_ja: str
    recovery_en: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def reader_error(stage: str, detail: str) -> ControlledError:
    prefix = "DXF" if stage == "DXF reader" else "STEP"
    return ControlledError(f"{prefix}-PARSE-001", "File validation", stage, f"The {prefix} file could not be processed safely.", f"{prefix}ファイルを安全に処理できませんでした。", f"Confirm that the file is a valid {prefix} file and is within the pilot limits. Safe detail: {detail}")
