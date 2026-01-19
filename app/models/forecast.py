from pydantic import BaseModel, Field
from typing import Any, Dict

class ForecastRequest(BaseModel):
    origin: str = Field(..., min_length=4, max_length=4, description="Origin ICAO")
    destination: str = Field(..., min_length=4, max_length=4, description="Destination ICAO")
    cruise_fl: int = Field(..., ge=0, le=600, description="Cruise flight level (e.g., 340)")
    calm: bool = Field(default=True, description="Passenger-friendly tone")
    embed: bool = False
    tier: str | None = "free"


class ForecastResponse(BaseModel):
    id: str
    briefing: str
    summary: Dict[str, Any]
    map_url: str
