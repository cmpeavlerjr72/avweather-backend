from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Tuple

from pyproj import Geod, Transformer
from shapely.geometry import LineString, mapping
from shapely.ops import transform as shp_transform

from app.data.airports_repo import airports_repo, AirportRecord


WGS84_GEOD = Geod(ellps="WGS84")


@dataclass(frozen=True)
class Airport:
    icao: str
    lat: float
    lon: float
    name: str = ""
    iata: str = ""


@dataclass(frozen=True)
class RouteGeometry:
    origin: Airport
    destination: Airport
    cruise_fl: int
    distance_nm: float
    route_points: List[Tuple[float, float]]  # [(lat, lon), ...]
    corridor_polygon_geojson: Dict           # GeoJSON dict
    corridor_bbox: Tuple[float, float, float, float]  # (min_lon, min_lat, max_lon, max_lat)


class RouteService:
    """
    Uses our local US airports dataset (OurAirports-derived).
    Input expects ICAO like KATL, KDEN.
    """

    def _to_airport(self, rec: AirportRecord) -> Airport:
        return Airport(
            icao=rec.icao,
            lat=rec.lat,
            lon=rec.lon,
            name=rec.name,
            iata=rec.iata,
        )

    def build_route(
        self,
        origin_icao: str,
        destination_icao: str,
        cruise_fl: int,
        corridor_nm: float = 50.0,
        point_spacing_nm: float = 25.0,
    ) -> RouteGeometry:
        origin_icao = origin_icao.strip().upper()
        destination_icao = destination_icao.strip().upper()

        if origin_icao == destination_icao:
            raise ValueError("Origin and destination must be different.")

        orec = airports_repo.get_by_icao(origin_icao)
        drec = airports_repo.get_by_icao(destination_icao)

        if not orec:
            raise ValueError(f"Unknown origin ICAO: {origin_icao}")
        if not drec:
            raise ValueError(f"Unknown destination ICAO: {destination_icao}")

        origin = self._to_airport(orec)
        dest = self._to_airport(drec)

        distance_m = WGS84_GEOD.line_length([origin.lon, dest.lon], [origin.lat, dest.lat])
        distance_nm = distance_m / 1852.0

        npts = max(2, int(math.ceil(distance_nm / point_spacing_nm)) + 1)
        intermediates = WGS84_GEOD.npts(origin.lon, origin.lat, dest.lon, dest.lat, npts - 2)
        route_lonlat = [(origin.lon, origin.lat)] + intermediates + [(dest.lon, dest.lat)]
        route_latlon = [(lat, lon) for (lon, lat) in route_lonlat]

        corridor_poly_geojson, bbox = self._build_corridor_polygon(route_lonlat, corridor_nm=corridor_nm)

        return RouteGeometry(
            origin=origin,
            destination=dest,
            cruise_fl=cruise_fl,
            distance_nm=distance_nm,
            route_points=route_latlon,
            corridor_polygon_geojson=corridor_poly_geojson,
            corridor_bbox=bbox,
        )

    def _build_corridor_polygon(self, route_lonlat: List[Tuple[float, float]], corridor_nm: float):
        buffer_m = corridor_nm * 1852.0

        line_wgs84 = LineString(route_lonlat)  # (lon, lat)

        fwd = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform
        inv = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True).transform

        line_3857 = shp_transform(fwd, line_wgs84)
        poly_3857 = line_3857.buffer(buffer_m)

        poly_wgs84 = shp_transform(inv, poly_3857)
        minx, miny, maxx, maxy = poly_wgs84.bounds

        return mapping(poly_wgs84), (minx, miny, maxx, maxy)
