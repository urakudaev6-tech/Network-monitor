"""Device inventory based on observations; no ICMP silence is treated as confirmed outage."""
import csv
import io
from datetime import datetime, timezone
from ipaddress import ip_address
from sqlalchemy import select
from app.db.database import SessionLocal
from app.db.models import NetworkScanORM, NetworkScanDeviceORM, NetworkEventORM, DeviceInventoryORM


def _record(row):
    return {"id": row.id, "subnet": row.subnet, "ip": row.ip,
            "label": row.label, "category": row.category, "notes": row.notes,
            "mac": row.mac, "hostname": row.hostname,
            "first_seen": row.first_seen.isoformat(), "last_seen": row.last_seen.isoformat(),
            "last_scan_at": row.last_scan_at.isoformat(), "detected_last_scan": row.detected_last_scan}


def update_inventory(session, scan, devices):
    """Call inside the scan persistence transaction."""
    for device in devices:
        ip = device["ip"]
        existing = session.scalar(select(DeviceInventoryORM).where(
            DeviceInventoryORM.subnet == scan.subnet, DeviceInventoryORM.ip == ip))
        if existing is None:
            if not device["detected"]:
                continue
            existing = DeviceInventoryORM(subnet=scan.subnet, ip=ip, label="", category="other", notes="",
                first_seen=scan.scanned_at, last_seen=scan.scanned_at, last_scan_at=scan.scanned_at,
                detected_last_scan=True, mac=device.get("mac"), hostname=device.get("hostname"))
            session.add(existing)
            continue
        existing.last_scan_at = scan.scanned_at
        existing.detected_last_scan = device["detected"]
        if device["detected"]:
            existing.last_seen = scan.scanned_at
            if device.get("mac"):
                existing.mac = device["mac"]
            if device.get("hostname"):
                existing.hostname = device["hostname"]


def list_devices(subnet=None, search="", limit=1000):
    with SessionLocal() as session:
        stmt = select(DeviceInventoryORM)
        if subnet:
            stmt = stmt.where(DeviceInventoryORM.subnet == subnet)
        rows = session.scalars(stmt.order_by(DeviceInventoryORM.subnet, DeviceInventoryORM.ip).limit(limit)).all()
        result = [_record(r) for r in rows]
        if search:
            q = search.casefold()
            result = [r for r in result if any(q in str(r.get(k) or "").casefold()
                      for k in ("ip", "mac", "hostname", "label", "category", "notes"))]
        return sorted(result, key=lambda r: (r["subnet"], int(ip_address(r["ip"]))))


def update_device(device_id, payload):
    with SessionLocal() as session:
        row = session.get(DeviceInventoryORM, device_id)
        if row is None:
            return None
        row.label = payload.label.strip()
        row.category = payload.category
        row.notes = payload.notes.strip()
        session.commit()
        session.refresh(row)
        return _record(row)


def device_details(device_id):
    with SessionLocal() as session:
        row = session.get(DeviceInventoryORM, device_id)
        if row is None:
            return None
        result = _record(row)
        history = session.execute(
            select(NetworkScanORM.id, NetworkScanORM.scanned_at, NetworkScanDeviceORM.detected,
                   NetworkScanDeviceORM.mac, NetworkScanDeviceORM.hostname)
            .join(NetworkScanDeviceORM, NetworkScanDeviceORM.scan_id == NetworkScanORM.id)
            .where(NetworkScanORM.subnet == row.subnet, NetworkScanDeviceORM.ip == row.ip)
            .order_by(NetworkScanORM.id.desc()).limit(100)
        ).all()
        result["history"] = [{"scan_id": sid, "scanned_at": date.isoformat(), "detected": detected,
                              "mac": mac, "hostname": hostname} for sid, date, detected, mac, hostname in history]
        return result


def inventory_csv(subnet=None):
    rows = list_devices(subnet=subnet)
    buf = io.StringIO()
    writer = csv.writer(buf)
    fields = ["subnet", "ip", "label", "category", "mac", "hostname", "first_seen", "last_seen", "last_scan_at", "detected_last_scan", "notes"]
    writer.writerow(fields)
    for row in rows:
        writer.writerow([row[k] for k in fields])
    return '\ufeff' + buf.getvalue()
