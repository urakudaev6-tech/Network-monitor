"""HTTP-маршруты. Все операции — через MonitorService, никакого SQLAlchemy здесь."""

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool

from app.api.schemas import (
    CheckResultResponse,
    MonitorResultResponse,
    TargetCreate,
    TargetResponse,
)
from app.monitoring.engine import DuplicateIdError

router = APIRouter()


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