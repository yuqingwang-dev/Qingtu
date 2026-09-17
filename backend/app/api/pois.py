"""Read-only live POI preview for currently supported domestic cities."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import City
from app.services.live_poi_service import search_city_pois

router = APIRouter()


@router.get("/domestic/pois")
async def search_domestic_pois(city_id: int = Query(gt=0), keywords: str = Query(default="景点", min_length=1, max_length=80),
                              limit: int = Query(default=10, ge=1, le=25), db: Session = Depends(get_db)):
    city = db.query(City).filter(City.id == city_id).first()
    if not city:
        raise HTTPException(status_code=404, detail="城市未收录")
    if not city.is_domestic:
        raise HTTPException(status_code=400, detail="高德搜索当前仅接入已支持的国内城市")
    result, cached = await search_city_pois(city, keywords, limit)
    return {**result.model_dump(mode="json"), "cache_hit": cached}
