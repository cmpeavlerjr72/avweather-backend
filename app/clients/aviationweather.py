from __future__ import annotations

import re
from typing import Dict, List, Optional, TypedDict, Any
import httpx

from app.core.config import settings
from app.utils.cache import TTLCache

BASE = "https://aviationweather.gov/api/data"
METAR_URL = f"{BASE}/metar"
PIREP_URL = f"{BASE}/pirep"
G_AIRMET_URL = f"{BASE}/gairmet"
AIRSIGMET_URL = f"{BASE}/airsigmet"
TAF_URL = f"{BASE}/taf"


def _clean_station(st: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (st or "").upper())

class MetarInfo(TypedDict):
    raw: str
    flight_cat: Optional[str]  # VFR/MVFR/IFR/LIFR/None

class AviationWeatherClient:
    def __init__(self, cache: TTLCache, timeout_seconds: float | None = None):
        self.cache = cache
        self.timeout = timeout_seconds or settings.http_timeout_seconds

    async def fetch_metars(self, stations: List[str], hours: float = 3.0) -> Dict[str, MetarInfo]:
        stations = [_clean_station(s) for s in stations if s]
        stations = [s for s in stations if s]
        if not stations:
            return {}

        key = f"metar:ids:{hours}:{','.join(sorted(stations))}"
        cached = self.cache.get(key)
        if cached is not None:
            return cached

        params = {"ids": ",".join(stations), "format": "json", "hours": hours}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(METAR_URL, params=params)
            r.raise_for_status()
            data = r.json()

        out: Dict[str, MetarInfo] = {}
        for row in data:
            st = (row.get("icaoId") or row.get("stationId") or "").upper()
            raw = row.get("rawOb") or row.get("rawObs") or row.get("rawText") or ""
            cat = row.get("flightCat") or row.get("fltCat") or row.get("flightCategory")
            if isinstance(cat, str):
                cat = cat.strip().upper()
            else:
                cat = None
            if st and raw:
                out[st] = {"raw": raw, "flight_cat": cat}

        self.cache.set(key, out, ttl=settings.cache_ttl_seconds)
        return out

    async def fetch_metars_bbox(
        self,
        lat_min: float,
        lon_min: float,
        lat_max: float,
        lon_max: float,
        hours: float = 3.0,
    ) -> List[dict]:
        """
        Returns list of METAR rows with lat/lon, rawOb, and flightCat/fltCat when available.
        """
        bbox = f"{lat_min},{lon_min},{lat_max},{lon_max}"
        key = f"metar:bbox:{hours}:{bbox}"
        cached = self.cache.get(key)
        if cached is not None:
            return cached

        params = {"bbox": bbox, "format": "json", "hours": hours}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(METAR_URL, params=params)
            # AWC sometimes returns 204 when none; treat as empty
            if r.status_code == 204:
                self.cache.set(key, [], ttl=settings.cache_ttl_seconds)
                return []
            r.raise_for_status()
            data = r.json()

        rows = data if isinstance(data, list) else []
        self.cache.set(key, rows, ttl=settings.cache_ttl_seconds)
        return rows
    
    async def fetch_pireps_bbox(
        self,
        lat_min: float,
        lon_min: float,
        lat_max: float,
        lon_max: float,
        age_hours: float = 3.0,
    ) -> List[dict]:
        """
        Returns list of PIREP rows in bbox. age is in hours (AWC 'age' param).
        """
        bbox = f"{lat_min},{lon_min},{lat_max},{lon_max}"
        key = f"pirep:bbox:{age_hours}:{bbox}"
        cached = self.cache.get(key)
        if cached is not None:
            return cached

        params = {"bbox": bbox, "format": "json", "age": age_hours}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(PIREP_URL, params=params)
            if r.status_code == 204:
                self.cache.set(key, [], ttl=settings.cache_ttl_seconds)
                return []
            r.raise_for_status()
            data = r.json()

        rows = data if isinstance(data, list) else []
        self.cache.set(key, rows, ttl=settings.cache_ttl_seconds)
        return rows
    
    async def fetch_gairmet(
        self,
        product: str,
        hazard: str | None = None,
        fore: int | None = None,
    ) -> dict:
        """
        G-AIRMET GeoJSON for CONUS.
        product: sierra|tango|zulu
        hazard: optional filter (depends on product)
        fore: optional forecast hour (0/3/6/9/12)
        """
        product = (product or "").strip().lower()
        key = f"gairmet:{product}:{hazard or ''}:{fore or ''}"
        cached = self.cache.get(key)
        if cached is not None:
            return cached

        params: Dict[str, Any] = {"product": product, "format": "geojson"}
        if hazard:
            params["hazard"] = hazard
        if fore is not None:
            params["fore"] = fore

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(G_AIRMET_URL, params=params)
            if r.status_code == 204:
                self.cache.set(key, {"type": "FeatureCollection", "features": []}, ttl=settings.cache_ttl_seconds)
                return {"type": "FeatureCollection", "features": []}
            r.raise_for_status()
            data = r.json()

        if not isinstance(data, dict):
            data = {"type": "FeatureCollection", "features": []}

        self.cache.set(key, data, ttl=settings.cache_ttl_seconds)
        return data

    async def fetch_airsigmet(
        self,
        hazard: str | None = None,
        level: int | None = None,
    ) -> dict:
        """
        Domestic SIGMETs GeoJSON (includes convective/non-convective).
        hazard: optional conv|turb|ice|ifr (AWC supports subsets)
        """
        key = f"airsigmet:{hazard or ''}:{level or ''}"
        cached = self.cache.get(key)
        if cached is not None:
            return cached

        params: Dict[str, Any] = {"format": "geojson"}
        if hazard:
            params["hazard"] = hazard
        if level is not None:
            params["level"] = level

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(AIRSIGMET_URL, params=params)
            if r.status_code == 204:
                self.cache.set(key, {"type": "FeatureCollection", "features": []}, ttl=settings.cache_ttl_seconds)
                return {"type": "FeatureCollection", "features": []}
            r.raise_for_status()
            data = r.json()

        if not isinstance(data, dict):
            data = {"type": "FeatureCollection", "features": []}

        self.cache.set(key, data, ttl=settings.cache_ttl_seconds)
        return data
    
    async def fetch_taf(self, icao: str) -> dict | None:
        """
        Fetch latest TAF for a station (json). Returns normalized dict or None.
        """
        icao = (icao or "").strip().upper()
        key = f"taf:{icao}"
        cached = self.cache.get(key)
        if cached is not None:
            return cached

        params = {"ids": icao, "format": "json"}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(TAF_URL, params=params)
            if r.status_code == 204:
                self.cache.set(key, None, ttl=settings.cache_ttl_seconds)
                return None
            r.raise_for_status()
            data = r.json()

        if not isinstance(data, list) or not data:
            self.cache.set(key, None, ttl=settings.cache_ttl_seconds)
            return None

        row = data[0]
        out = {
            "icao": icao,
            "raw": row.get("rawTAF") or row.get("raw") or row.get("raw_text") or "",
            "issueTime": row.get("issueTime") or row.get("issue_time") or "",
        }
        self.cache.set(key, out, ttl=settings.cache_ttl_seconds)
        return out



