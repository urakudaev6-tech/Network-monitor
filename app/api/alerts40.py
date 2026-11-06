"""Network Monitor 4.0: read-only scan-derived alerts and persisted local rules."""
from __future__ import annotations
import json
import os
import threading
from pathlib import Path
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.services.network_history import list_scans, get_scan, list_events
from app.services.device_registry import list_devices

router = APIRouter(prefix="/alerts", tags=["alerts"])
LOCK = threading.RLock()
STATE_FILE = Path(__file__).resolve().parents[2] / "data" / "network40_alerts.json"
DEFAULTS = {"missed_scans": 2, "new_ip": True, "mac_changed": True,
            "hostname_changed": True, "detected_again": True, "missed_ping": True}

def _read():
    with LOCK:
        if not STATE_FILE.exists():
            return {"rules": DEFAULTS.copy(), "acknowledged": []}
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            rules = DEFAULTS | {k: v for k, v in data.get("rules", {}).items() if k in DEFAULTS}
            ack = [str(x) for x in data.get("acknowledged", []) if isinstance(x, str)][:10000]
            return {"rules": rules, "acknowledged": ack}
        except (OSError, ValueError, TypeError):
            raise HTTPException(500, "Alert settings cannot be read; no changes made")

def _write(data):
    with LOCK:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_name(STATE_FILE.name + ".tmp")
        try:
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, STATE_FILE)
        finally:
            if tmp.exists():
                tmp.unlink()

class Rules(BaseModel):
    missed_scans: int = Field(2, ge=1, le=10)
    new_ip: bool = True
    mac_changed: bool = True
    hostname_changed: bool = True
    detected_again: bool = True
    missed_ping: bool = True

class Ack(BaseModel):
    acknowledged: bool = True

def _snapshot():
    state = _read()
    rules = state["rules"]
    ack = set(state["acknowledged"])
    scans = list_scans(15)
    devices = list_devices()
    events = list_events(300)
    alerts = []
    for e in events:
        kind = e.get("kind", "")
        if kind not in ("new_ip", "mac_changed", "hostname_changed", "detected_again") or not rules.get(kind):
            continue
        aid = "event:" + str(e["id"])
        alerts.append({"id": aid, "kind": kind, "ip": e["ip"], "scan_id": e["scan_id"],
                       "message": {"new_ip": "Новый IP", "mac_changed": "Изменился MAC",
                                   "hostname_changed": "Изменилось имя", "detected_again": "Снова обнаружен"}[kind],
                       "severity": "warning" if kind == "mac_changed" else "info",
                       "acknowledged": aid in ack})
    # A failed ICMP probe is not proof that a device is powered off.
    if rules["missed_ping"] and scans:
        recent = scans[:rules["missed_scans"]]
        if len(recent) >= rules["missed_scans"]:
            details = [get_scan(s["id"]) for s in recent]
            newest = details[0]
            if newest:
                for d in newest.get("devices", []):
                    ip = d["ip"]
                    if d.get("detected"):
                        continue
                    if all(x and x.get("subnet") == newest["subnet"] and any(
                        item["ip"] == ip and not item["detected"] for item in x.get("devices", [])
                    ) for x in details):
                        aid = f"missed:{newest['subnet']}:{ip}:{recent[0]['id']}"
                        alerts.append({"id": aid, "kind": "missed_ping", "ip": ip,
                                       "scan_id": recent[0]["id"], "message": f"Нет ответа на {rules['missed_scans']} сканированиях (не доказательство отключения)",
                                       "severity": "warning", "acknowledged": aid in ack})
    return {"rules": rules, "alerts": alerts[:500], "stats": {
        "registered": len(devices), "responding_last_scan": sum(bool(d.get("detected_last_scan")) for d in devices),
        "not_responding_last_scan": sum(not d.get("detected_last_scan") for d in devices),
        "scans": len(scans), "last_scan": scans[0] if scans else None,
        "unacknowledged": sum(not a["acknowledged"] for a in alerts[:500])},
        "notice": "Отсутствие ICMP-ответа не доказывает отключение устройства. Уведомления показываются в веб-интерфейсе; отправка email/push не включена."}

@router.get("")
def get_alerts():
    return _snapshot()

@router.put("/rules")
def set_rules(rules: Rules):
    with LOCK:
        data = _read()
        data["rules"] = rules.model_dump() if hasattr(rules, "model_dump") else rules.dict()
        _write(data)
    return {"rules": data["rules"]}

@router.patch("/{alert_id:path}/ack")
def acknowledge(alert_id: str, payload: Ack):
    if len(alert_id) > 160 or not alert_id.startswith(("event:", "missed:")):
        raise HTTPException(422, "Invalid alert ID")
    with LOCK:
        data = _read()
        ack = set(data["acknowledged"])
        if payload.acknowledged:
            ack.add(alert_id)
        else:
            ack.discard(alert_id)
        data["acknowledged"] = sorted(ack)[-10000:]
        _write(data)
    return {"id": alert_id, "acknowledged": payload.acknowledged}


# NM41_BULK_ACK_V1: one atomic update, limited to alerts visible in the snapshot.
class BulkAck(BaseModel):
    ids: list[str] = Field(default_factory=list, max_length=500)
    acknowledged: bool = True

@router.post("/bulk-ack")
def bulk_ack(payload: BulkAck):
    if len(payload.ids) != len(set(payload.ids)):
        raise HTTPException(422, "Duplicate alert IDs")
    if any(not isinstance(x, str) or len(x) > 160 for x in payload.ids):
        raise HTTPException(422, "Invalid alert ID")
    with LOCK:
        valid = {a["id"] for a in _snapshot()["alerts"]}
        if not set(payload.ids).issubset(valid):
            raise HTTPException(422, "Unknown or expired alert ID")
        data = _read()
        ack = set(data["acknowledged"])
        if payload.acknowledged:
            ack.update(payload.ids)
        else:
            ack.difference_update(payload.ids)
        data["acknowledged"] = sorted(ack)[-10000:]
        _write(data)
    return {"updated": len(payload.ids), "acknowledged": payload.acknowledged}
