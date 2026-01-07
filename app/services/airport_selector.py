from __future__ import annotations

from typing import List
from shapely.geometry import Point, shape

from app.data.airports_repo import airports_repo, AirportRecord

def airports_in_corridor(route, limit: int = 12) -> List[AirportRecord]:
    """
    MVP selection:
    - candidates within corridor bbox
    - then point-in-polygon
    - return up to `limit`
    """
    poly = shape(route.corridor_polygon_geojson)  # polygon in lon/lat
    min_lon, min_lat, max_lon, max_lat = route.corridor_bbox

    out: List[AirportRecord] = []
    for rec in airports_repo.all():
        if rec.lon < min_lon or rec.lon > max_lon or rec.lat < min_lat or rec.lat > max_lat:
            continue
        if poly.contains(Point(rec.lon, rec.lat)):
            out.append(rec)
            if len(out) >= limit:
                break

    return out
