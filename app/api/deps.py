import time
from fastapi import Request, HTTPException, Depends

from app.core.config import settings
from app.storage.map_store import MapStore
from app.services.forecast_service import ForecastService
from app.services.route_service import RouteService
from app.services.map_service import MapService

from app.utils.cache import TTLCache
from app.clients.aviationweather import AviationWeatherClient

from app.utils.cache import TTLCache
from app.clients.aviationweather import AviationWeatherClient
from app.services.route_service import RouteService
from app.services.map_service import MapService


_rate_bucket = {}  # ip -> (window_start_epoch, count)
_cache = TTLCache(default_ttl=settings.cache_ttl_seconds)

async def rate_limit(request: Request):
    ip = request.client.host if request.client else "unknown"
    now = int(time.time())
    window = now - (now % 60)

    win_start, count = _rate_bucket.get(ip, (window, 0))
    if win_start != window:
        win_start, count = window, 0

    count += 1
    _rate_bucket[ip] = (win_start, count)

    if count > settings.rate_limit_per_minute:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again in a minute.")

def get_map_store() -> MapStore:
    return MapStore(maps_dir=settings.maps_dir, ttl_seconds=settings.map_ttl_seconds)

def get_aviationweather_client() -> AviationWeatherClient:
    return AviationWeatherClient(cache=_cache, timeout_seconds=settings.http_timeout_seconds)

def get_forecast_service(
    store: MapStore = Depends(get_map_store),
    aw: AviationWeatherClient = Depends(get_aviationweather_client),
) -> ForecastService:
    return ForecastService(
        map_store=store,
        route_service=RouteService(),
        map_service=MapService(),
        aviationweather=aw,
    )


