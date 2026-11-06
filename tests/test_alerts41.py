"""Network Monitor 4.1: bulk acknowledgement is atomic and validated."""
from fastapi import HTTPException
from app.api import alerts40


def test_bulk_ack_validates_unknown(monkeypatch, tmp_path):
    monkeypatch.setattr(alerts40, "STATE_FILE", tmp_path / "alerts.json")
    monkeypatch.setattr(alerts40, "_snapshot", lambda: {"alerts": [{"id": "event:1"}]})
    try:
        alerts40.bulk_ack(alerts40.BulkAck(ids=["event:unknown"]))
    except HTTPException as exc:
        assert exc.status_code == 422
    else:
        raise AssertionError("Unknown IDs must be rejected")
    assert not (tmp_path / "alerts.json").exists()


def test_bulk_ack_persists_and_reverses(monkeypatch, tmp_path):
    monkeypatch.setattr(alerts40, "STATE_FILE", tmp_path / "alerts.json")
    monkeypatch.setattr(alerts40, "_snapshot", lambda: {"alerts": [{"id": "event:1"}, {"id": "event:2"}]})
    assert alerts40.bulk_ack(alerts40.BulkAck(ids=["event:1", "event:2"]))["updated"] == 2
    assert set(alerts40._read()["acknowledged"]) == {"event:1", "event:2"}
    alerts40.bulk_ack(alerts40.BulkAck(ids=["event:1"], acknowledged=False))
    assert alerts40._read()["acknowledged"] == ["event:2"]


def test_bulk_ack_rejects_duplicates(monkeypatch, tmp_path):
    monkeypatch.setattr(alerts40, "STATE_FILE", tmp_path / "alerts.json")
    monkeypatch.setattr(alerts40, "_snapshot", lambda: {"alerts": [{"id": "event:1"}]})
    try:
        alerts40.bulk_ack(alerts40.BulkAck(ids=["event:1", "event:1"]))
    except HTTPException as exc:
        assert exc.status_code == 422
    else:
        raise AssertionError("Duplicate IDs must be rejected")
