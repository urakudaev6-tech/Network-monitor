from app.services.network_history import scan_quality
from app.monitoring.network_scanner import _permanent_probe_error


def test_quality_baseline():
    assert not scan_quality(238, None)["suspicious"]


def test_quality_detects_drop():
    result = scan_quality(127, 238)
    assert result["suspicious"]
    assert result["drop_count"] == 111
    assert result["drop_percent"] == 46.6


def test_quality_ignores_small_changes():
    assert not scan_quality(237, 238)["suspicious"]
    assert not scan_quality(0, 0)["suspicious"]


def test_retry_error_classification():
    assert _permanent_probe_error("ping not found")
    assert not _permanent_probe_error("Device did not respond")
