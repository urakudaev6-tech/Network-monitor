from app.monitoring import network_scanner as scanner


def test_retry_recovers_device(monkeypatch):
    calls = {}

    def fake_probe(ip, timeout):
        calls[ip] = calls.get(ip, 0) + 1
        detected = calls[ip] >= 2
        return {
            "ip": ip,
            "detected": detected,
            "mac": None,
            "hostname": None,
            "latency_ms": 1.0 if detected else None,
            "error": None if detected else "?????????? ??????????",
        }

    monkeypatch.setattr(scanner, "_probe", fake_probe)

    result = scanner.scan_subnet(
        "192.168.1.0/30", "192.168.1.0/24",
        retries=1,
    )

    assert result["total"] == 2
    assert result["detected"] == 2
    assert all(count == 2 for count in calls.values())


def test_no_retry(monkeypatch):
    calls = []

    def fake_probe(ip, timeout):
        calls.append(ip)
        return {
            "ip": ip, "detected": False,
            "mac": None, "hostname": None,
            "latency_ms": None,
            "error": "?????????? ??????????",
        }

    monkeypatch.setattr(scanner, "_probe", fake_probe)

    result = scanner.scan_subnet(
        "192.168.1.0/30", "192.168.1.0/24",
        retries=0,
    )

    assert result["detected"] == 0
    assert len(calls) == 2


def test_arp_matches_exact_ip(monkeypatch):
    class Completed:
        stdout = (
            "  192.168.1.20   aa-bb-cc-dd-ee-ff dynamic\n"
            "  192.168.1.21   11-22-33-44-55-66 dynamic\n"
        )

    monkeypatch.setattr(
        scanner.subprocess, "run",
        lambda *args, **kwargs: Completed(),
    )

    assert scanner._mac_from_arp("192.168.1.21") == "11:22:33:44:55:66"
    assert scanner._mac_from_arp("192.168.1.22") is None
