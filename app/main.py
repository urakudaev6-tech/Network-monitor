"""Точка входа FastAPI + фоновый планировщик мониторинга."""

import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import settings
from app.monitoring.engine import MonitorEngine
from app.services.monitor_service import MonitorService


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
        task = None
        if settings.scheduler_interval > 0 and session_factory is not None:
            task = asyncio.create_task(
                _scheduler_loop(service, settings.scheduler_interval)
            )
        try:
            yield
        finally:
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
    app.include_router(router)
    return app


app = create_app()