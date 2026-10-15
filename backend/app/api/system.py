"""Safe service diagnostics. No credentials are ever returned."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.service_status import build_status

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status")
async def system_status(
    probe_llm: bool = Query(False, description="是否发起一次真实模型请求；可能消耗配额"),
    db: Session = Depends(get_db),
):
    return await build_status(db, probe_llm=probe_llm)
