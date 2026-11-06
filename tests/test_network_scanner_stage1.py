import pytest
from app.monitoring import network_scanner as scanner

def test_requires_explicit_allowlist():
    with pytest.raises(PermissionError):
        scanner.scan_subnet("192.168.1.0/30", "")

def test_disallows_outside_network():
    with pytest.raises(PermissionError):
        scanner.scan_subnet("10.0.0.0/30", "192.168.0.0/16")

def test_limits_subnet_size():
    with pytest.raises(ValueError):
        scanner.scan_subnet("192.168.0.0/16", "192.168.0.0/16")

def test_scan_results(monkeypatch):
    monkeypatch.setattr(scanner, "_probe", lambda ip, timeout: {
        "ip": ip, "detected": ip.endswith(".1"), "mac": None,
        "hostname": None, "latency_ms": None, "error": None})
    result = scanner.scan_subnet("192.168.1.0/30", "192.168.1.0/24")
    assert result["total"] == 2
    assert result["detected"] == 1
    assert result["not_detected"] == 1
