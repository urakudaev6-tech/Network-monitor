import math
import platform
import re
import subprocess


def _validate_host(host):
    if not isinstance(host, str):
        return f"host не может быть не в строчном виде"
    if not host.strip():
        return f"host не может быть пустым"
    return None
def _validate_timeout(timeout):
    if isinstance(timeout, bool):
        return "timeout не может быть bool"
    if not isinstance(timeout, (int, float)):
        return f"timeout должен быть числом"
    if not math.isfinite(timeout):
        return f"timeout должен быть конечным числом, получено {timeout}"
    if timeout <= 0:
        return f"timeout должен быть > 0, получено {timeout}"
    return None
def _build_ping_command(host: str, timeout: float):
    if platform.system()== "Windows":
        return ["ping", "-n", "1", "-w", str(int(timeout * 1000)), host]
    return ["ping", "-c", "1", "-W", str(max(1, int(round(timeout)))), host]
def _run_ping(cmd: list[str], timeout: float):
    if platform.system() == "Windows":
        encoding = "cp866"
    else:
        encoding = "utf-8"
    try:
        proc = subprocess.run(cmd,capture_output=True,text=True,encoding=encoding,errors="replace",timeout=timeout + 1)
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except FileNotFoundError:
        return -1, "", "ping не найден в системе"
    except PermissionError:
        return -1, "", "ping есть, но нет прав на запуск"
    except OSError as e:
        return -1, "", f"ошибка запуска ping: {e}"
    except subprocess.TimeoutExpired:
        return -2, "", "процесс ping не завершился вовремя"
    
def _parse_ping_ms(output: str):
    m = re.search(
        r"(?:время|time)\s*[=<]\s*(\d+(?:[.,]\d+)?)\s*(?:мсек|мс|ms)",
        output,
        re.IGNORECASE,
    )
    if not m:
        return None
    raw = m.group(1).replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None
def check_icmp(host: str, timeout: float = 2.0) -> dict:
    result = {"host": host, "ok": False, "ms": None, "error": None}
    error = _validate_host(host) or _validate_timeout(timeout)
    if error:
        result["error"] = error
        return result
    cmd = _build_ping_command(host, timeout)
    rc, stdout, stderr = _run_ping(cmd, timeout)
    if rc == -1:
        result["error"] = stderr or "ping не запустился"
        return result
    if rc == -2:
        result["error"] = "Слишком долгое выполнение ping" + (f": {stderr}" if stderr else "")
        return result
    has_ttl = "ttl=" in stdout.lower()
    if rc == 0 or has_ttl:
        result["ok"] = True
        result["ms"] = _parse_ping_ms(stdout)
        if result["ms"] is None:
            result["error"] = "Не удалось извлечь время из ответа ping"
        return result
    if "не удалось обнаружить узел" in stdout or "unknown host" in stdout.lower():
        result["error"] = "dns-ошибка: не удалось разрешить host"
    elif stderr:
        result["error"] = f"ping завершился с ошибкой: {stderr.strip()}"
    else:
        result["error"] = "Устройство недоступно"

    return result

if __name__ == "__main__":
    cases = [
        ("127.0.0.1", 2.0),
        ("192.0.2.1", 2.0),
        ("no-such-host.invalid", 2.0),
        ("", 2.0),
        ("example.com", -1),
        ("10.255.255.1", 1.0),
    ]
    for host, timeout in cases:
        print(check_icmp(host, timeout))