from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status

from backend.api.deps import get_current_user_id
from backend.inference.service import (
    LocalModelStatus,
    ManagedModelStatus,
    ModelInstallRequest,
    ModelRemovalResult,
    cancel_managed_model_install,
    get_local_model_catalog,
    get_local_model_status,
    install_managed_model,
    pause_managed_model_install,
    remove_managed_model,
    replace_managed_model,
    restart_managed_model,
    resume_managed_model_install,
)

router = APIRouter()


@router.get("/status", response_model=LocalModelStatus)
async def status() -> LocalModelStatus:
    return await get_local_model_status()


@router.get("/catalog")
def catalog() -> dict[str, object]:
    return get_local_model_catalog()


@router.post(
    "/install",
    response_model=ManagedModelStatus,
    status_code=http_status.HTTP_202_ACCEPTED,
)
async def install(
    payload: ModelInstallRequest,
    _user_id: int = Depends(get_current_user_id),
) -> ManagedModelStatus:
    try:
        return await install_managed_model(payload)
    except (KeyError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/replace",
    response_model=ManagedModelStatus,
    status_code=http_status.HTTP_202_ACCEPTED,
)
async def replace(
    payload: ModelInstallRequest,
    _user_id: int = Depends(get_current_user_id),
) -> ManagedModelStatus:
    try:
        return await replace_managed_model(payload)
    except (KeyError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/cancel", response_model=ManagedModelStatus)
async def cancel(_user_id: int = Depends(get_current_user_id)) -> ManagedModelStatus:
    return await cancel_managed_model_install()


@router.post("/pause", response_model=ManagedModelStatus)
def pause(_user_id: int = Depends(get_current_user_id)) -> ManagedModelStatus:
    try:
        return pause_managed_model_install()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/resume", response_model=ManagedModelStatus)
async def resume(_user_id: int = Depends(get_current_user_id)) -> ManagedModelStatus:
    try:
        return await resume_managed_model_install()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("", response_model=ModelRemovalResult)
async def remove(_user_id: int = Depends(get_current_user_id)) -> ModelRemovalResult:
    return await remove_managed_model()


@router.post("/restart", response_model=ManagedModelStatus)
async def restart(_user_id: int = Depends(get_current_user_id)) -> ManagedModelStatus:
    try:
        return await restart_managed_model()
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
