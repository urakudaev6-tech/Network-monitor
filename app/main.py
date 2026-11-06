"""Точка входа FastAPI + фоновый планировщик мониторинга."""

import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.api.alerts40 import router as alerts40_router  # NM40_ALERT_CENTER_V1
from app.security10 import gateway as security10_gateway
from app.config import settings
from app.monitoring.engine import MonitorEngine
from app.services.monitor_service import MonitorService
from app.monitoring.network_scanner import scan_subnet
from app.services.network_history import save_scan
from datetime import datetime, timezone
import ipaddress

# NETWORK30_SCHEDULED_SCANNER
async def _auto_scan_loop(app: FastAPI) -> None:
    """Opt-in subnet scanning, sequential, with bounded scan parameters."""
    cfg = settings
    state = app.state.auto_scan
    while True:
        state['running'] = True
        state['last_started'] = datetime.now(timezone.utc).isoformat()
        try:
            result = await run_in_threadpool(
                scan_subnet, cfg.auto_scan_subnet, cfg.scan_allowed_cidrs,
                cfg.auto_scan_timeout, cfg.auto_scan_workers, cfg.auto_scan_retries
            )
            await run_in_threadpool(save_scan, result)
            state['last_completed'] = datetime.now(timezone.utc).isoformat()
            state['last_detected'] = result['detected']
            state['last_total'] = result['total']
            state['last_error'] = None
        except Exception as exc:
            state['last_error'] = f'{type(exc).__name__}: {str(exc)[:180]}'
            print(f"[auto-scan] {state['last_error']}", flush=True)
        finally:
            state['running'] = False
        await asyncio.sleep(cfg.auto_scan_interval)


def _validate_auto_scan() -> None:
    cfg = settings
    if not cfg.auto_scan_enabled:
        return
    if not cfg.auto_scan_subnet or not cfg.scan_allowed_cidrs:
        raise RuntimeError('Auto scan requires AUTO_SCAN_SUBNET and SCAN_ALLOWED_CIDRS')
    subnet = ipaddress.ip_network(cfg.auto_scan_subnet, strict=True)
    if subnet.version != 4 or subnet.num_addresses > 1024:
        raise RuntimeError('Auto scan requires an IPv4 CIDR with at most 1024 addresses')
    if not any(subnet.subnet_of(ipaddress.ip_network(x.strip(), strict=False))
               for x in cfg.scan_allowed_cidrs.split(',') if x.strip()):
        raise RuntimeError('AUTO_SCAN_SUBNET is not included in SCAN_ALLOWED_CIDRS')
    if not 300 <= cfg.auto_scan_interval <= 86400:
        raise RuntimeError('AUTO_SCAN_INTERVAL must be between 300 and 86400 seconds')
    if not 0.2 <= cfg.auto_scan_timeout <= 5 or not 1 <= cfg.auto_scan_workers <= 64 or not 0 <= cfg.auto_scan_retries <= 2:
        raise RuntimeError('Invalid auto scan timeout/workers/retries')



async def _scheduler_loop(service: MonitorService, interval: int) -> None:
    """Каждые `interval` секунд запускает мониторинг. Не накладывает циклы."""
    while True:
        try:
            await run_in_threadpool(service.run_monitoring)
        except Exception as e:
            # Один цикл упал — не роняем планировщик
            print(f"[scheduler] error: {e}")
        await asyncio.sleep(interval)


def create_app(session_factory=None) -> FastAPI:
    if session_factory is None:
        from app.db.database import SessionLocal, engine as db_engine, init_db
        session_factory = SessionLocal
        if str(db_engine.url).startswith("sqlite"):
            init_db()

    monitor_engine = MonitorEngine([])
    service = MonitorService(monitor_engine, session_factory)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        service.load_from_db()
        _validate_auto_scan()
        auto_task = None
        if settings.auto_scan_enabled:
            auto_task = asyncio.create_task(_auto_scan_loop(_app))
        task = None
        if settings.scheduler_interval > 0 and session_factory is not None:
            task = asyncio.create_task(
                _scheduler_loop(service, settings.scheduler_interval)
            )
        try:
            yield
        finally:
            if auto_task is not None:
                auto_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await auto_task
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(title="Network Monitor API", version="0.4.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.engine = monitor_engine
    app.state.service = service
    app.state.auto_scan = {
        'running': False, 'last_started': None, 'last_completed': None,
        'last_detected': None, 'last_total': None, 'last_error': None,
    }
    app.middleware("http")(security10_gateway)
    app.include_router(router)
    app.include_router(alerts40_router)
    return app


app = create_app()