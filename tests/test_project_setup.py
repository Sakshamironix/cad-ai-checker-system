"""Tests that verify the current application identity and capability."""

from app.main import APP_NAME, APP_STAGE, get_app_status


def test_app_status_describes_milestone_nine() -> None:
    status = get_app_status()

    assert status["application"] == APP_NAME
    assert status["stage"] == APP_STAGE
    assert "マイルストーン9" in status["stage"]
    assert status["capability"] == (
        "Deterministic comparison with vector mismatch overlay / "
        "ベクター不一致表示付きの決定論的比較"
    )
