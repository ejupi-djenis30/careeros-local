from fastapi import APIRouter

from backend.inference.service import LocalModelStatus, get_local_model_status

router = APIRouter()


@router.get("/status", response_model=LocalModelStatus)
async def status() -> LocalModelStatus:
    return await get_local_model_status()
