from __future__ import annotations

from pathlib import Path

from app.dxf_reader import DxfReaderError, analyze_dxf_bytes
from app.step_reader import StepReaderError, analyze_step_bytes


def test_empty_uploads_return_controlled_errors() -> None:
    try:
        analyze_dxf_bytes(b"", "drawing.dxf")
    except DxfReaderError as error:
        assert "empty" in str(error).lower()
    try:
        analyze_step_bytes(b"", "model.step")
    except StepReaderError as error:
        assert "empty" in str(error).lower()


def test_uploaded_names_are_not_used_as_filesystem_paths(tmp_path: Path) -> None:
    try:
        analyze_dxf_bytes(b"bad", "../../untrusted.dxf")
    except DxfReaderError:
        assert not (tmp_path / "untrusted.dxf").exists()
