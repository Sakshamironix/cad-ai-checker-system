"""Tests that verify the Milestone 1 application foundation."""

from app.main import APP_NAME, APP_STAGE, get_app_status


def test_app_status_describes_milestone_one() -> None:
    status = get_app_status()

    assert status["application"] == APP_NAME
    assert status["stage"] == APP_STAGE
    assert status["capability"] == "STEP/STP topology and geometry analysis"
