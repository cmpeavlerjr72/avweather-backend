from pydantic import BaseModel
from typing import Optional

class AirportSearchResult(BaseModel):
    icao: str
    iata: Optional[str] = None
    name: str
    municipality: Optional[str] = None
    region: Optional[str] = None
    lat: float
    lon: float
    scheduled_service: Optional[str] = None
    type: Optional[str] = None
    score: int
