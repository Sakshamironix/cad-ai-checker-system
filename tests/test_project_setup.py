"""Tests that verify the current application identity and capability."""

from app.main import APP_NAME, APP_STAGE, get_app_status


def test_app_status_describes_milestone_ten() -> None:
    status = get_app_status()

    assert status["application"] == APP_NAME
    assert status["stage"] == APP_STAGE
    assert "マイルストーン10" in status["stage"]
    assert status["capability"] == (
        "Downloadable judgement-first JSON and PDF reports / "
        "判定優先のJSON・PDFレポートダウンロード"
    )
