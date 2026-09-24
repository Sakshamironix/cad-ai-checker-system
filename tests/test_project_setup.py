"""Application identity follows the running geometry engine."""
from app.main import APP_NAME, APP_STAGE, get_app_status
from app.geometry_check import ENGINE_VERSION

def test_app_status_describes_active_engine():
    status = get_app_status()
    assert status["application"] == APP_NAME
    assert status["stage"] == APP_STAGE
    assert status["version"] == ENGINE_VERSION
