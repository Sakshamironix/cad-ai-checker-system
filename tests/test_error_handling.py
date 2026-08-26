from __future__ import annotations

from app.error_catalog import reader_error


def test_reader_error_has_bilingual_safe_recovery_evidence() -> None:
    error = reader_error("STEP reader", "untrusted parser message")
    assert error.error_id == "STEP-PARSE-001"
    assert "STEP" in error.message_en and "ファイル" in error.message_ja
    assert "untrusted parser message" in error.recovery_en
