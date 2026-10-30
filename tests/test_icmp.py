"""Тесты для app.monitoring.icmp. Без сети и без реального ping."""

import importlib
import subprocess

import pytest

import app.monitoring.icmp as icmp_module
from app.monitoring.icmp import (
    _build_ping_command,
    _parse_ping_ms,
    _run_ping,
)


# ---------- Валидация ----------


def test_host_empty():
    r = icmp_module.check_icmp("")
    assert r["ok"] is False
    assert "пуст" in r["error"]


def test_host_none():
    r = icmp_module.check_icmp(None)
    assert r["ok"] is False
    assert r["error"] is not None


def test_host_int():
    r = icmp_module.check_icmp(123)
    assert r["ok"] is False
    assert r["error"] is not None


@pytest.mark.parametrize("bad_timeout", [0, -1, -0.001])
def test_timeout_non_positive(bad_timeout):
    r = icmp_module.check_icmp("example.com", timeout=bad_timeout)
    assert r["ok"] is False
    assert "timeout" in r["error"]


def test_timeout_inf():
    r = icmp_module.check_icmp("example.com", timeout=float("inf"))
    assert r["ok"] is False
    assert "конечным" in r["error"]


def test_timeout_nan():
    r = icmp_module.check_icmp("example.com", timeout=float("nan"))
    assert r["ok"] is False


def test_timeout_string():
    r = icmp_module.check_icmp("example.com", timeout="5")
    assert r["ok"] is False


def test_timeout_bool():
    r = icmp_module.check_icmp("example.com", timeout=True)
    assert r["ok"] is False
    assert "bool" in r["error"]


# ---------- _build_ping_command ----------


def test_build_command_windows(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Windows")
    cmd = _build_ping_command("127.0.0.1", 2.0)
    assert cmd == ["ping", "-n", "1", "-w", "2000", "127.0.0.1"]


def test_build_command_linux(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Linux")
    cmd = _build_ping_command("127.0.0.1", 2.0)
    assert cmd == ["ping", "-c", "1", "-W", "2", "127.0.0.1"]


# ---------- _parse_ping_ms ----------


def test_parse_windows_lt_1_ru():
    assert _parse_ping_ms("Ответ ... время<1мс TTL=128") == 1.0


def test_parse_windows_lt_1_en():
    assert _parse_ping_ms("Reply ... time<1ms TTL=128") == 1.0


def test_parse_windows_exact_ru():
    assert _parse_ping_ms("... время=12мс TTL=118") == 12.0


def test_parse_windows_exact_ms():
    assert _parse_ping_ms("... время=12мсек TTL=118") == 12.0


def test_parse_linux():
    assert _parse_ping_ms("64 bytes from ...: time=0.045 ms") == 0.045


def test_parse_linux_no_space():
    assert _parse_ping_ms("64 bytes from ...: time=0.045ms") == 0.045


def test_parse_uppercase():
    assert _parse_ping_ms("Time=12ms TTL=64") == 12.0


def test_parse_comma():
    assert _parse_ping_ms("... time=1,5 ms") == 1.5


def test_parse_no_match():
    assert _parse_ping_ms("При проверке связи не удалось обнаружить узел") is None


# ---------- _run_ping: исключения ----------


def test_run_ping_file_not_found(monkeypatch):
    def fake(*a, **kw):
        raise FileNotFoundError
    monkeypatch.setattr(subprocess, "run", fake)
    rc, out, err = _run_ping(["ping", "x"], 1.0)
    assert rc == -1
    assert "не найден" in err


def test_run_ping_permission(monkeypatch):
    def fake(*a, **kw):
        raise PermissionError
    monkeypatch.setattr(subprocess, "run", fake)
    rc, out, err = _run_ping(["ping", "x"], 1.0)
    assert rc == -1
    assert "прав" in err


def test_run_ping_oserror(monkeypatch):
    def fake(*a, **kw):
        raise OSError("generic")
    monkeypatch.setattr(subprocess, "run", fake)
    rc, out, err = _run_ping(["ping", "x"], 1.0)
    assert rc == -1
    assert "ошибка запуска" in err


def test_run_ping_timeout(monkeypatch):
    def fake(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="ping", timeout=1)
    monkeypatch.setattr(subprocess, "run", fake)
    rc, out, err = _run_ping(["ping", "x"], 1.0)
    assert rc == -2


# ---------- check_icmp с моком _run_ping ----------


def test_success_windows_ping(monkeypatch):
    monkeypatch.setattr(
        icmp_module, "_run_ping",
        lambda cmd, t: (0, "Ответ ... время<1мс TTL=128", ""),
    )
    r = icmp_module.check_icmp("127.0.0.1")
    assert r["ok"] is True
    assert r["ms"] == 1.0


def test_success_linux_ping(monkeypatch):
    monkeypatch.setattr(
        icmp_module, "_run_ping",
        lambda cmd, t: (0, "64 bytes from 127.0.0.1: ... time=0.045 ms", ""),
    )
    r = icmp_module.check_icmp("127.0.0.1")
    assert r["ok"] is True
    assert r["ms"] == 0.045


def test_rc0_without_ttl_still_ok(monkeypatch):
    # Основной признак — rc == 0, даже если TTL нет (машина рецензента)
    monkeypatch.setattr(
        icmp_module, "_run_ping",
        lambda cmd, t: (0, "какой-то вывод без TTL и без времени", ""),
    )
    r = icmp_module.check_icmp("127.0.0.1")
    assert r["ok"] is True
    assert r["ms"] is None
    assert "время" in r["error"].lower()


def test_rc1_with_ttl_is_ok(monkeypatch):
    # Странный случай: rc != 0, но хост ответил
    monkeypatch.setattr(
        icmp_module, "_run_ping",
        lambda cmd, t: (1, "TTL=128", ""),
    )
    r = icmp_module.check_icmp("127.0.0.1")
    assert r["ok"] is True


def test_dns_error(monkeypatch):
    monkeypatch.setattr(
        icmp_module, "_run_ping",
        lambda cmd, t: (1, "При проверке связи не удалось обнаружить узел no-such.invalid", ""),
    )
    r = icmp_module.check_icmp("no-such.invalid")
    assert r["ok"] is False
    assert "dns" in r["error"].lower()


def test_unreachable(monkeypatch):
    monkeypatch.setattr(
        icmp_module, "_run_ping",
        lambda cmd, t: (1, "Превышен интервал ожидания. 100% потерь.", ""),
    )
    r = icmp_module.check_icmp("10.255.255.1")
    assert r["ok"] is False
    assert "доступно" in r["error"]


def test_unreachable_with_stderr(monkeypatch):
    monkeypatch.setattr(
        icmp_module, "_run_ping",
        lambda cmd, t: (1, "", "some ping error"),
    )
    r = icmp_module.check_icmp("10.255.255.1")
    assert r["ok"] is False
    assert "some ping error" in r["error"]


def test_ping_not_found_uses_stderr(monkeypatch):
    monkeypatch.setattr(
        icmp_module, "_run_ping",
        lambda cmd, t: (-1, "", "ping не найден в системе"),
    )
    r = icmp_module.check_icmp("127.0.0.1")
    assert r["ok"] is False
    assert "не найден" in r["error"]


def test_ping_no_permission_uses_stderr(monkeypatch):
    monkeypatch.setattr(
        icmp_module, "_run_ping",
        lambda cmd, t: (-1, "", "ping есть, но нет прав на запуск"),
    )
    r = icmp_module.check_icmp("127.0.0.1")
    assert r["ok"] is False
    assert "прав" in r["error"]


def test_ping_process_timeout(monkeypatch):
    monkeypatch.setattr(
        icmp_module, "_run_ping",
        lambda cmd, t: (-2, "", "процесс ping не завершился вовремя"),
    )
    r = icmp_module.check_icmp("127.0.0.1")
    assert r["ok"] is False
    assert "долгое" in r["error"].lower()


# ---------- Импорт не запускает демо ----------


def test_import_does_not_run_demo(monkeypatch, capsys):
    def fake(*a, **kw):
        raise AssertionError("subprocess.run вызван при импорте")
    monkeypatch.setattr(subprocess, "run", fake)
    importlib.reload(icmp_module)
    assert capsys.readouterr().out == ""