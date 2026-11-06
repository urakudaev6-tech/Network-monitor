"""HTTP-маршруты. Все операции — через MonitorService, никакого SQLAlchemy здесь."""

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from fastapi.concurrency import run_in_threadpool

from app.api.schemas import (
    CheckResultResponse,
    MonitorResultResponse,
    TargetCreate,
    TargetResponse,
)
from app.monitoring.engine import DuplicateIdError
from app.monitoring.network_scanner import scan_subnet
from app.config import settings
from app.api.schemas import ScanRequest, ScanResponse, DeviceUpdate
from app.services.network_history import save_scan, list_scans, get_scan, list_events

from app.services.device_registry import list_devices, update_device, device_details, inventory_csv
from app.services.email_reports import send_report

router = APIRouter()

# NETWORK30_SCHEDULED_SCANNER
@router.get('/monitor/auto-scan/status')
def auto_scan_status(request: Request):
    # Protected by the existing Security 1.0 gateway.
    return {
        'enabled': settings.auto_scan_enabled,
        'subnet': settings.auto_scan_subnet if settings.auto_scan_enabled else None,
        'interval_seconds': settings.auto_scan_interval,
        **request.app.state.auto_scan,
    }



@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/targets", response_model=list[TargetResponse])
def list_targets(request: Request):
    return request.app.state.service.list_targets()


@router.get("/targets/{target_id}", response_model=TargetResponse)
def get_target(target_id: int, request: Request):
    t = request.app.state.service.get_target(target_id)
    if t is None:
        raise HTTPException(status_code=404, detail=f"id={target_id} не найден")
    return t


@router.get("/targets/{target_id}/history", response_model=list[CheckResultResponse])
def get_history(
    target_id: int,
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000),
):
    history = request.app.state.service.get_history(target_id, limit=limit)
    if history is None:
        raise HTTPException(status_code=404, detail=f"id={target_id} не найден")
    return history


@router.post("/targets", response_model=TargetResponse, status_code=201)
def add_target(payload: TargetCreate, request: Request):
    try:
        return request.app.state.service.add_target(
            host=payload.host,
            type_=payload.type,
            port=payload.port,
            timeout=payload.timeout,
            id_=payload.id,
        )
    except DuplicateIdError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.delete("/targets/{target_id}", status_code=204)
def delete_target(target_id: int, request: Request):
    if not request.app.state.service.delete_target(target_id):
        raise HTTPException(status_code=404, detail=f"id={target_id} не найден")


@router.post("/monitor/run", response_model=list[MonitorResultResponse])
async def run_monitor(request: Request):
    try:
        return await run_in_threadpool(request.app.state.service.run_monitoring)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/monitor/results", response_model=list[MonitorResultResponse])
def get_results(request: Request):
    return request.app.state.service.get_last_results()

@router.post("/scanner/scan", response_model=ScanResponse)
async def run_subnet_scan(payload: ScanRequest):
    """Scan only explicitly permitted CIDRs. Keep this endpoint VPN-only."""
    try:
        result = await run_in_threadpool(
            scan_subnet, payload.subnet, settings.scan_allowed_cidrs, payload.timeout, payload.workers, payload.retries
        )
        await run_in_threadpool(save_scan, result)
        return result
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/scanner/history")
def scan_history(limit: int = Query(default=30, ge=1, le=100)):
    return list_scans(limit)


@router.get("/scanner/history/{scan_id}")
def scan_history_details(scan_id: int):
    result = get_scan(scan_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Сканирование не найдено")
    return result


@router.get("/scanner/events")
def scan_events(limit: int = Query(default=100, ge=1, le=500)):
    return list_events(limit)


@router.get("/scanner/devices")
def scanner_devices(subnet: str | None = None, search: str = ""):
    return list_devices(subnet=subnet, search=search[:200])


@router.get("/scanner/devices/export")
def scanner_devices_export(subnet: str | None = None):
    return Response(content=inventory_csv(subnet), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="network_devices.csv"'})


@router.get("/scanner/devices/{device_id}")
def scanner_device_details(device_id: int):
    item = device_details(device_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Устройство не найдено")
    return item


@router.patch("/scanner/devices/{device_id}")
def scanner_device_update(device_id: int, payload: DeviceUpdate):
    item = update_device(device_id, payload)
    if item is None:
        raise HTTPException(status_code=404, detail="Устройство не найдено")
    return item


@router.post("/scanner/email-report")
async def scanner_email_report(request: Request):
    # The existing API has no authentication. Do not expose this action remotely.
    if request.client is None or request.client.host not in ("127.0.0.1", "::1"):
        raise HTTPException(status_code=403, detail="Отправка разрешена только с локального компьютера")
    try:
        return await run_in_threadpool(send_report)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        # Avoid leaking SMTP secrets or network details to browser.
        raise HTTPException(status_code=502, detail="Не удалось отправить письмо. Проверьте SMTP и журнал сервера") from exc
