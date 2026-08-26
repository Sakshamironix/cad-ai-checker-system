"""Tests that verify the current application identity and capability."""

from app.main import APP_NAME, APP_STAGE, get_app_status


def test_app_status_describes_milestone_sixteen() -> None:
    status = get_app_status()

    assert status["application"] == APP_NAME
    assert status["stage"] == APP_STAGE
    assert "マイルストーン16" in status["stage"]
    assert status["version"] == "CAD AI Checker v0.16.0-pilot"
    assert status["capability"] == (
        "Guarded bilingual discrepancy explanations after deterministic OK or NG\n"
        "決定論的OK・NG判定後の保護された日英不一致説明"
    )
