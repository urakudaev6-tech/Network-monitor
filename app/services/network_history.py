"""Persist authorized scan results and compare reliable observations."""
from datetime import datetime
from sqlalchemy import select
from app.db.database import SessionLocal
from app.db.models import NetworkScanORM, NetworkScanDeviceORM, NetworkEventORM
from app.services.device_registry import update_inventory


def _scan_dict(scan):
    return {"id": scan.id, "subnet": scan.subnet, "scanned_at": scan.scanned_at.isoformat(),
            "total": scan.total, "detected": scan.detected, "not_detected": scan.not_detected}


def _device_dict(d):
    return {"ip": d.ip, "detected": d.detected, "mac": d.mac, "hostname": d.hostname,
            "latency_ms": d.latency_ms, "error": d.error}


def _event_dict(e):
    return {"id": e.id, "scan_id": e.scan_id, "ip": e.ip, "kind": e.kind,
            "old_value": e.old_value, "new_value": e.new_value}


def scan_quality(current_detected: int, previous_detected: int | None) -> dict:
    """Compare consecutive scans of the same subnet; never infer host availability."""
    if previous_detected is None:
        return {"previous_detected": None, "drop_count": 0, "drop_percent": 0.0, "suspicious": False}
    drop = max(0, previous_detected - current_detected)
    pct = round(100.0 * drop / previous_detected, 1) if previous_detected > 0 else 0.0
    return {"previous_detected": previous_detected, "drop_count": drop,
            "drop_percent": pct, "suspicious": drop >= 20 and pct >= 25.0}


def save_scan(result):
    with SessionLocal() as session:
        previous = session.scalars(select(NetworkScanORM).where(NetworkScanORM.subnet == result["subnet"])
                                   .order_by(NetworkScanORM.id.desc()).limit(1)).first()
        quality = scan_quality(result["detected"], previous.detected if previous else None)
        result["quality"] = quality
        if quality["suspicious"]:
            warning = (
                f"Scan quality warning: detected count fell from {quality['previous_detected']} "
                f"to {result['detected']} (-{quality['drop_percent']}%). "
                "This may indicate scan or network conditions; no-response IPs are not confirmed free."
            )
            result["warning"] = (result.get("warning", "") + " " + warning).strip()
        old = {}
        if previous:
            old = {d.ip: d for d in session.scalars(select(NetworkScanDeviceORM)
                   .where(NetworkScanDeviceORM.scan_id == previous.id)).all()}
        scan = NetworkScanORM(subnet=result["subnet"], scanned_at=datetime.fromisoformat(result["scanned_at"]),
                              total=result["total"], detected=result["detected"], not_detected=result["not_detected"])
        session.add(scan)
        session.flush()
        events = []
        for d in result["devices"]:
            session.add(NetworkScanDeviceORM(scan_id=scan.id, **d))
            before = old.get(d["ip"])
            if not d["detected"]:
                # ICMP silence is not evidence of departure; do not mark as offline.
                continue
            if before is None or not before.detected:
                # Only call it new when a previous scan exists; first scan is baseline.
                if previous:
                    events.append((d["ip"], "detected_again" if before else "new_ip", None, d.get("mac")))
            elif before.mac and d.get("mac") and before.mac.lower() != d["mac"].lower():
                events.append((d["ip"], "mac_changed", before.mac, d["mac"]))
            if before and before.detected and before.hostname and d.get("hostname") and before.hostname != d["hostname"]:
                events.append((d["ip"], "hostname_changed", before.hostname, d["hostname"]))
        for ip, kind, old_value, new_value in events:
            session.add(NetworkEventORM(scan_id=scan.id, ip=ip, kind=kind,
                                        old_value=old_value, new_value=new_value))
        update_inventory(session, scan, result["devices"])
        session.commit()
        return scan.id


def list_scans(limit=30):
    with SessionLocal() as session:
        scans = session.scalars(select(NetworkScanORM).order_by(NetworkScanORM.id.desc()).limit(limit)).all()
        return [_scan_dict(s) for s in scans]


def get_scan(scan_id):
    with SessionLocal() as session:
        scan = session.get(NetworkScanORM, scan_id)
        if scan is None:
            return None
        result = _scan_dict(scan)
        previous = session.scalars(select(NetworkScanORM)
            .where(NetworkScanORM.subnet == scan.subnet, NetworkScanORM.id < scan.id)
            .order_by(NetworkScanORM.id.desc()).limit(1)).first()
        result["quality"] = scan_quality(scan.detected, previous.detected if previous else None)
        result["devices"] = [_device_dict(d) for d in session.scalars(
            select(NetworkScanDeviceORM).where(NetworkScanDeviceORM.scan_id == scan_id).order_by(NetworkScanDeviceORM.ip)).all()]
        result["events"] = [_event_dict(e) for e in session.scalars(
            select(NetworkEventORM).where(NetworkEventORM.scan_id == scan_id).order_by(NetworkEventORM.id)).all()]
        return result


def list_events(limit=100):
    with SessionLocal() as session:
        events = session.scalars(select(NetworkEventORM).order_by(NetworkEventORM.id.desc()).limit(limit)).all()
        return [_event_dict(e) for e in events]
