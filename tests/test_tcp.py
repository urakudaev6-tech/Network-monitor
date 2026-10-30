"""Тесты для app.monitoring.tcp.check_tcp.

Стратегия:
- Успешное подключение — локальный сервер на свободном порту (без интернета).
- Отказ (refused) — свободный порт, который никто не слушает.
- Timeout / DNS — мок socket.create_connection (без ожидания и без сети).

Никакие тесты не ходят в интернет. Работают на любой машине, всегда.
"""

import socket
import threading

import pytest

from app.monitoring.tcp import check_tcp


# ---------- Фикстуры ----------


@pytest.fixture
def local_server():
    """Локальный TCP-сервер на свободном порту. Принимает одно подключение."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))          # 0 = ОС выберет свободный порт
    port = srv.getsockname()[1]
    srv.listen(1)

    def accept_one():
        try:
            conn, _ = srv.accept()
            conn.close()
        except OSError:
            pass

    t = threading.Thread(target=accept_one, daemon=True)
    t.start()
    try:
        yield port
    finally:
        srv.close()
        t.join(timeout=1)


@pytest.fixture
def closed_port():
    """Свободный порт, который НЕ слушается -> гарантированный refused."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ---------- Успешное подключение ----------


def test_success_returns_ok_and_ms(local_server):
    r = check_tcp("127.0.0.1", local_server, timeout=2)
    assert r["ok"] is True
    assert r["error"] is None
    assert isinstance(r["ms"], float)
    assert r["ms"] >= 0


def test_ms_rounded_to_two_decimals(local_server):
    r = check_tcp("127.0.0.1", local_server, timeout=2)
    assert r["ms"] == round(r["ms"], 2)


# ---------- Валидация порта ----------


@pytest.mark.parametrize("bad_port", [0, -1, 65536, 100000])
def test_port_out_of_range(bad_port):
    r = check_tcp("example.com", bad_port)
    assert r["ok"] is False
    assert "диапазон" in r["error"]


def test_port_is_string():
    r = check_tcp("example.com", "80")
    assert r["ok"] is False
    assert "int" in r["error"]


def test_port_is_bool():
    r = check_tcp("example.com", True)
    assert r["ok"] is False
    assert "bool" in r["error"]


def test_port_is_float():
    r = check_tcp("example.com", 80.5)
    assert r["ok"] is False
    assert "int" in r["error"]


# ---------- Валидация timeout ----------


@pytest.mark.parametrize("bad_timeout", [0, -1, -0.001])
def test_timeout_non_positive(bad_timeout):
    r = check_tcp("example.com", 80, timeout=bad_timeout)
    assert r["ok"] is False
    assert "timeout" in r["error"]


def test_timeout_infinite():
    r = check_tcp("example.com", 80, timeout=float("inf"))
    assert r["ok"] is False
    assert "конечным" in r["error"]


def test_timeout_nan():
    r = check_tcp("example.com", 80, timeout=float("nan"))
    assert r["ok"] is False


def test_timeout_is_string():
    r = check_tcp("example.com", 80, timeout="5")
    assert r["ok"] is False
    assert "числом" in r["error"]


def test_timeout_is_bool():
    r = check_tcp("example.com", 80, timeout=True)
    assert r["ok"] is False
    assert "bool" in r["error"]


# ---------- Валидация host ----------


def test_host_empty():
    r = check_tcp("", 80)
    assert r["ok"] is False
    assert "пуст" in r["error"]


def test_host_none():
    r = check_tcp(None, 80)
    assert r["ok"] is False
    assert "строкой" in r["error"]


# ---------- Сетевые ошибки через мок ----------


def test_timeout_error(monkeypatch):
    def fake(*args, **kwargs):
        raise socket.timeout("simulated")

    monkeypatch.setattr(socket, "create_connection", fake)
    r = check_tcp("example.com", 80, timeout=1)
    assert r["ok"] is False
    assert "долгое" in r["error"]


def test_dns_error(monkeypatch):
    def fake(*args, **kwargs):
        raise socket.gaierror("no such host")

    monkeypatch.setattr(socket, "create_connection", fake)
    r = check_tcp("no-such-host.invalid", 80)
    assert r["ok"] is False
    assert "dns" in r["error"].lower()


def test_connection_refused(monkeypatch):
    def fake(*args, **kwargs):
        raise ConnectionRefusedError("simulated")

    monkeypatch.setattr(socket, "create_connection", fake)
    r = check_tcp("127.0.0.1", 12345, timeout=1)
    assert r["ok"] is False
    assert "отказ" in r["error"]
def test_import_does_not_run_demo(monkeypatch, capsys):
    """Импорт модуля не должен запускать демо-код (3 сетевых запроса + print)."""
    import importlib
    import app.monitoring.tcp as tcp_module

    # Перехватываем create_connection: если демо-код выполнится, мок вызовется
    calls = []
    def fake(*args, **kwargs):
        calls.append(args)
        raise AssertionError("create_connection вызван при импорте — демо-код не под __main__")

    monkeypatch.setattr(socket, "create_connection", fake)

    # Перезагружаем модуль — имитируем «первый импорт»
    importlib.reload(tcp_module)

    # Ни одного сетевого вызова
    assert calls == []
    # Ничего не напечатано
    captured = capsys.readouterr()
    assert captured.out == ""