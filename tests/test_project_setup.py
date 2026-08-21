"""Tests that verify the current application identity and capability."""

from app.main import APP_NAME, APP_STAGE, get_app_status


def test_app_status_describes_milestone_twelve() -> None:
    status = get_app_status()

    assert status["application"] == APP_NAME
    assert status["stage"] == APP_STAGE
    assert "マイルストーン12" in status["stage"]
    assert status["capability"] == (
        "Guarded bilingual discrepancy explanations after deterministic OK/NG / "
        "決定論的OK/NG判定後の保護された日英不一致説明"
    )
