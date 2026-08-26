from __future__ import annotations

from app.health import check_health


def test_pilot_health_check_is_offline_and_reports_all_required_checks() -> None:
    status = check_health()
    assert set(status.checks) == {"libraries", "configuration", "temporary_storage"}
    assert status.healthy
