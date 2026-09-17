"""Public, bounded read-only travel knowledge endpoints."""
import asyncio
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from app.db.session import get_db
from app.db.models import City, KnowledgeDocument, KnowledgeChunk
from app.services.knowledge_embeddings import MODEL, DIMENSIONS
from app.services.knowledge_service import retrieve, select_with_ai

router = APIRouter(prefix="/knowledge", tags=["旅行知识库"])
_capacity = asyncio.Semaphore(2)


class Question(BaseModel):
    city_id: int = Field(gt=0)
    question: str = Field(min_length=2, max_length=500)
    poi_name: str | None = Field(default=None, max_length=150)
    travel_date: date | None = None
    use_ai: bool = False


@router.get("/status")
def status(db: Session = Depends(get_db)):
    docs = list(db.scalars(select(KnowledgeDocument).order_by(KnowledgeDocument.source_key)))
    return {"documents": len(docs), "chunks": db.scalar(select(func.count(KnowledgeChunk.id))),
            "embedding_model": MODEL, "dimensions": DIMENSIONS,
            "coverage": sorted({d.poi_name for d in docs}),
            "sources": [{"title": d.title, "url": d.url, "reviewed_on": d.reviewed_on,
                         "expires_on": d.expires_on, "city": d.city, "poi_name": d.poi_name} for d in docs]}


@router.post("/ask")
async def ask(request: Question, db: Session = Depends(get_db)):
    if _capacity.locked():
        raise HTTPException(429, "攻略问答繁忙，请稍后重试")
    async with _capacity:
        def search():
            city = db.get(City, request.city_id)
            if city is None:
                raise HTTPException(404, "城市不存在")
            return retrieve(db, city.name_zh or city.name, request.question, request.poi_name, request.travel_date)
        result = await run_in_threadpool(search)
        return await select_with_ai(request.question, result) if request.use_ai else result
