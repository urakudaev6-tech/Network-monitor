"""Bounded, explicitly authorized IPv4 subnet discovery for Windows/Linux."""
from __future__ import annotations
import concurrent.futures
import ipaddress
import platform
import re
import socket
import subprocess
from datetime import datetime, timezone
from app.monitoring.icmp import check_icmp


def _allowed(network: ipaddress.IPv4Network, allowed_cidrs: str) -> bool:
    allowed = [x.strip() for x in allowed_cidrs.split(",") if x.strip()]
    if not allowed:
        return False
    return any(network.subnet_of(ipaddress.IPv4Network(item, strict=False)) for item in allowed)


def _mac_from_arp(ip: str) -> str | None:
    try:
        completed = subprocess.run(
            ["arp", "-a", ip],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    mac_pattern = (
        r"([0-9a-fA-F]{2}(?:[:-][0-9a-fA-F]{2}){5})"
    )

    for line in completed.stdout.splitlines():
        parts = line.split()
        if not parts or parts[0] != ip:
            continue
        if len(parts) < 2:
            continue
        match = re.fullmatch(mac_pattern, parts[1])
        if match:
            return match.group(1).replace("-", ":").lower()

    return None


def _hostname(ip: str) -> str | None:
    try:
        return socket.gethostbyaddr(ip)[0]
    except (socket.herror, socket.gaierror, OSError):
        return None


def _probe(ip: str, timeout: float) -> dict:
    check = check_icmp(ip, timeout)
    detected = bool(check["ok"])
    return {"ip": ip, "detected": detected,
            "mac": _mac_from_arp(ip) if detected else None,
            "hostname": _hostname(ip) if detected else None,
            "latency_ms": check["ms"] if detected else None,
            "error": None if detected else check["error"]}


def _permanent_probe_error(error: str | None) -> bool:
    if not error:
        return False
    value = error.casefold()
    # Errors indicating the local ping executable is unavailable.
    return any(term in value for term in (
        "ping not found", "ping executable not found", "ping command not found",
        "ping is not recognized", "no such file or directory",
        "не найден", "не распознан", "не удалось найти",
    ))


def scan_subnet(cidr: str, allowed_cidrs: str, timeout: float = 0.8, workers: int = 32, retries: int = 1) -> dict:
    try:
        network = ipaddress.ip_network(cidr, strict=False)
    except ValueError as exc:
        raise ValueError("Некорректная подсеть CIDR") from exc
    if not isinstance(network, ipaddress.IPv4Network):
        raise ValueError("Поддерживается только IPv4")
    if network.num_addresses > 256:
        raise ValueError("Максимальный размер сканирования — /24 (256 адресов)")
    try:
        authorized = _allowed(network, allowed_cidrs)
    except ValueError as exc:
        raise ValueError("Некорректная конфигурация SCAN_ALLOWED_CIDRS") from exc
    if not authorized:
        raise PermissionError("Подсеть не разрешена в SCAN_ALLOWED_CIDRS")
    if not 0.2 <= timeout <= 5.0 or not 1 <= workers <= 64 or not 0 <= retries <= 2:
        raise ValueError("Недопустимые параметры сканирования")
    hosts = [str(host) for host in network.hosts()]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        devices = list(executor.map(lambda ip: _probe(ip, timeout), hosts))

        for _ in range(retries):
            pending = [
                (index, device["ip"])
                for index, device in enumerate(devices)
                if not device["detected"]
                and not _permanent_probe_error(device.get("error"))
            ]
            if not pending:
                break

            repeated = list(
                executor.map(
                    lambda item: _probe(item[1], timeout),
                    pending,
                )
            )
            for (index, _), result in zip(pending, repeated):
                devices[index] = result
    return {"subnet": str(network), "scanned_at": datetime.now(timezone.utc).isoformat(),
            "total": len(devices), "detected": sum(d["detected"] for d in devices),
            "not_detected": sum(not d["detected"] for d in devices),
            "devices": devices,
            "warning": "Отсутствие ответа на ping не доказывает, что IP свободен. Проверяйте DHCP, резервации и ARP."}
