from fastapi import APIRouter, Depends, Query
from typing import List

from app.api.deps import rate_limit
from app.data.airports_repo import airports_repo
from app.models.airports import AirportSearchResult

router = APIRouter()

@router.get("/airports/search", response_model=List[AirportSearchResult])
async def search_airports(
    q: str = Query(..., min_length=1, max_length=64),
    limit: int = Query(10, ge=1, le=25),
    _=Depends(rate_limit),
):
    results = airports_repo.search(q=q, limit=limit)
    out: List[AirportSearchResult] = []
    for rec, score in results:
        out.append(AirportSearchResult(
            icao=rec.icao,
            iata=rec.iata or None,
            name=rec.name,
            municipality=rec.municipality or None,
            region=rec.region or None,
            lat=rec.lat,
            lon=rec.lon,
            scheduled_service=rec.scheduled_service or None,
            type=rec.type or None,
            score=score,
        ))
    return out
