import socket
import time
import math


def _validate_port(port) -> str | None:
    if isinstance(port, bool):
        return "порт не может быть bool"
    if not isinstance(port, int):
        return f"порт должен быть int, получено {type(port).__name__}"
    if port < 1 or port > 65535:
        return f"порт {port} вне диапазона 1..65535"
    
    return None 

def _validate_timeout(timeout) -> str | None:
    if isinstance(timeout, bool):
        return "timeout не может быть bool"
    if not isinstance(timeout, (int, float)):
        return f"timeout должен быть числом, получено {type(timeout).__name__}"
    if not math.isfinite(timeout):
        return f"timeout должен быть конечным числом, получено {timeout}"
    if timeout <= 0:
        return f"timeout должен быть > 0, получено {timeout}"
    
    return None  
def _validate_host(host) -> str | None:
    if not isinstance(host, str):
        return f"host должен быть строкой, получено {type(host).__name__}"
    if not host.strip():                    
        return "host не может быть пустым"
    return None 

def check_tcp(host:str,port:int,timeout: float=5.0)->dict:
    result = {"host": host, "port": port, "ok": False, "ms": None, "error": None}
    
    error = (
    _validate_host(host)
    or _validate_port(port)
    or _validate_timeout(timeout)
    )
    if error:
        result["error"] = error
        return result
    
    start=time.perf_counter()
 
    try:
        with socket.create_connection((host,port),timeout=timeout):
            result["ok"]=True
    except socket.timeout:
        result["error"] = "Слишком долгое подключение"
    except ConnectionRefusedError:
        result["error"] = "В соединении отказано"
    except socket.gaierror as e:
        result["error"] = f"dns-ошибка: {e}"
    except OSError as e:
        result["error"] = f"os-ошибка: {e}"
    finally:
        result["ms"] = round((time.perf_counter() - start) * 1000, 2)
                    
    return result
if __name__ == "__main__":
    targets = [
        ("example.com", 80),
        ("google.com", 443),
        ("ya.ru", 80)]

    for host,port in targets:
        r=check_tcp(host,port,timeout=5)
        print(r)
        