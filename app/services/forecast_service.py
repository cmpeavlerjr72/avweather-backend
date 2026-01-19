from app.models.forecast import ForecastRequest, ForecastResponse
from app.storage.map_store import MapStore
from app.utils.ids import new_id
from app.services.airport_selector import airports_in_corridor
from app.services.briefing_service import BriefingService, BriefingInputs
from shapely.geometry import Point, shape

from shapely.geometry import shape as shp_shape

def _normalize_hazard_props(props: dict) -> dict:
    """Ensure a stable 'hazard' label exists for Folium tooltips."""
    if not isinstance(props, dict):
        props = {}
    hz = props.get("hazard") or props.get("phenom") or props.get("type") or props.get("label")
    if not hz:
        # sometimes AWC uses different keys; last resort:
        hz = props.get("rawHazard") or "unknown"
    props["hazard"] = str(hz)
    return props

def _normalize_featurecollection_hazard(gj: dict) -> dict:
    """Return a FeatureCollection where every feature has properties['hazard']."""
    if not isinstance(gj, dict):
        return {"type": "FeatureCollection", "features": []}
    feats = gj.get("features") or []
    out = []
    for f in feats:
        if not isinstance(f, dict):
            continue
        props = _normalize_hazard_props(f.get("properties") or {})
        f["properties"] = props
        out.append(f)
    return {"type": "FeatureCollection", "features": out}


def _to_fl(v) -> int | None:
    if v is None:
        return None
    try:
        s = str(v).upper().replace("FL", "").strip()
        return int(s)
    except Exception:
        return None
    
def _poly_overlaps_alt(props: dict, cruise_fl: int, pad_fl: int = 20) -> bool:
    lo = props.get("minAlt") or props.get("min_alt")
    hi = props.get("maxAlt") or props.get("max_alt")
    lo_fl = _to_fl(lo)
    hi_fl = _to_fl(hi)
    if lo_fl is None or hi_fl is None:
        return True  # unknown altitude -> keep (don’t hide)
    return (lo_fl - pad_fl) <= cruise_fl <= (hi_fl + pad_fl)

def _clip_geojson_to_corridor(geojson: dict, corridor_poly, cruise_fl: int) -> dict:
    if not geojson or not isinstance(geojson, dict) or corridor_poly is None:
        return {"type": "FeatureCollection", "features": []}
    feats = []
    for f in geojson.get("features", []) or []:
        try:
            geom = f.get("geometry")
            props = f.get("properties", {}) or {}
            shp = shp_shape(geom)
            if not shp.is_valid:
                continue
            if not shp.intersects(corridor_poly):
                continue
            if not _poly_overlaps_alt(props, cruise_fl):
                continue
            feats.append(f)
        except Exception:
            continue
    return {"type": "FeatureCollection", "features": feats}

def _pirep_intensity(p: dict) -> str | None:
    vals = [
        str(p.get("tbInt1") or "").upper(),
        str(p.get("tbInt2") or "").upper(),
        str(p.get("icgInt1") or "").upper(),
        str(p.get("icgInt2") or "").upper(),
    ]
    if any("SEV" in v for v in vals):
        return "SEV"
    if any("MOD" in v for v in vals):
        return "MOD"
    if any("LGT" in v for v in vals):
        return "LGT"
    return None


class ForecastService:
    def __init__(self, map_store: MapStore, route_service, map_service, aviationweather):
        self.map_store = map_store
        self.route_service = route_service
        self.map_service = map_service
        self.aviationweather = aviationweather

    async def generate(self, req: ForecastRequest) -> ForecastResponse:
        map_id = new_id()

        # 1) Route + corridor
        route = self.route_service.build_route(
            origin_icao=req.origin,
            destination_icao=req.destination,
            cruise_fl=req.cruise_fl,
        )

        # 2) Choose a limited set of corridor airports (surface context)
        corridor_airports = airports_in_corridor(route, limit=12)
        metar_stations = [req.origin, req.destination] + [a.icao for a in corridor_airports]

        # de-dupe while preserving order
        seen = set()
        metar_stations = [s for s in metar_stations if not (s in seen or seen.add(s))]

        # 3) Fetch METARs (surface)
        metar_rows = []
        missing_products = []

        try:
            # route.corridor_bbox is (min_lon, min_lat, max_lon, max_lat)
            min_lon, min_lat, max_lon, max_lat = route.corridor_bbox

            rows = await self.aviationweather.fetch_metars_bbox(
                lat_min=min_lat, lon_min=min_lon, lat_max=max_lat, lon_max=max_lon, hours=3.0
            )

            poly = shape(route.corridor_polygon_geojson)

            # Keep only those inside corridor polygon
            inside = []
            for row in rows:
                lat = row.get("lat")
                lon = row.get("lon")
                if lat is None or lon is None:
                    continue
                if poly.contains(Point(lon, lat)):
                    inside.append(row)

            # Limit to avoid clutter
            metar_rows = inside[:40]
            # Add layman interpretations for map popups
            try:
                bs = BriefingService()
                for r in metar_rows:
                    raw = (r.get("rawOb") or r.get("rawObs") or r.get("rawText") or r.get("raw") or "").strip()
                    icao = (r.get("icaoId") or r.get("stationId") or "").strip()
                    if raw:
                        r["plain"] = bs.interpret_metar(raw, station=icao)
            except Exception as e:
                # Keep map functional, but expose why plain text is missing
                for r in metar_rows:
                    if "plain" not in r:
                        r["plain"] = f"(Interpretation unavailable: {type(e).__name__})"



        except Exception:
            missing_products.append("metar")
            metar_rows = []

        # 3b) Fetch PIREPs (aloft) in bbox, then corridor + altitude filtering
        pirep_rows = []
        try:
            min_lon, min_lat, max_lon, max_lat = route.corridor_bbox
            rows = await self.aviationweather.fetch_pireps_bbox(
                lat_min=min_lat, lon_min=min_lon, lat_max=max_lat, lon_max=max_lon, age_hours=3.0
            )

            poly = shape(route.corridor_polygon_geojson)

            cruise_fl = int(req.cruise_fl)
            band_fl = 40  # ±40 FL = ±4000 ft-ish band

            inside = []
            for p in rows:
                lat = p.get("lat")
                lon = p.get("lon")
                if lat is None or lon is None:
                    continue
                if not poly.contains(Point(lon, lat)):
                    continue

                fl = _to_fl(p.get("fltLvl"))
                # keep if unknown level OR within band
                if fl is None or (cruise_fl - band_fl) <= fl <= (cruise_fl + band_fl):
                    inside.append(p)

            # calm mode: show only MOD+ to avoid scaring people with lots of light reports
            if req.calm:
                inside = [p for p in inside if (_pirep_intensity(p) in ("MOD", "SEV"))]

            pirep_rows = inside[:60]
            # Add layman interpretations for map popups
            try:
                bs = BriefingService()
                for p in pirep_rows:
                    raw = (p.get("rawOb") or p.get("raw") or "").strip()
                    fl = p.get("fltLvl") or ""
                    if raw:
                        p["plain"] = bs.interpret_pirep(raw, fl=fl)
            except Exception as e:
                for p in pirep_rows:
                    if "plain" not in p:
                        p["plain"] = f"(Interpretation unavailable: {type(e).__name__})"



        except Exception:
            missing_products.append("pirep")
            pirep_rows = []

        pirep_counts = {"LGT": 0, "MOD": 0, "SEV": 0, "UNK": 0}
        for p in pirep_rows:
            lvl = _pirep_intensity(p)
            pirep_counts[lvl or "UNK"] += 1

                # 3c) Fetch advisories (G-AIRMET + SIGMET) and clip to corridor
        gairmet = {"type": "FeatureCollection", "features": []}
        sigmet = {"type": "FeatureCollection", "features": []}

        try:
            corridor_poly = shape(route.corridor_polygon_geojson)

            # G-AIRMETs: Tango (turb), Zulu (icing), Sierra (IFR/mtn obs)
            gj_tango = await self.aviationweather.fetch_gairmet(product="tango")
            gj_zulu = await self.aviationweather.fetch_gairmet(product="zulu")
            gj_sierra = await self.aviationweather.fetch_gairmet(product="sierra")

            gairmet = {
                "tango": _normalize_featurecollection_hazard(
                    _clip_geojson_to_corridor(gj_tango, corridor_poly, int(req.cruise_fl))
                ),
                "zulu": _normalize_featurecollection_hazard(
                    _clip_geojson_to_corridor(gj_zulu, corridor_poly, int(req.cruise_fl))
                ),
                "sierra": _normalize_featurecollection_hazard(
                    _clip_geojson_to_corridor(gj_sierra, corridor_poly, int(req.cruise_fl))
                ),
            }

            # Domestic SIGMETs (all)
            sig_all = await self.aviationweather.fetch_airsigmet()
            sigmet = _clip_geojson_to_corridor(sig_all, corridor_poly, int(req.cruise_fl))
            sigmet = _normalize_featurecollection_hazard(sigmet)

        except Exception:
            missing_products.append("gairmet")
            missing_products.append("sigmet")
            gairmet = {"tango": {"type": "FeatureCollection", "features": []},
                       "zulu": {"type": "FeatureCollection", "features": []},
                       "sierra": {"type": "FeatureCollection", "features": []}}
            sigmet = {"type": "FeatureCollection", "features": []}

        def _feat_count(gj: dict) -> int:
            try:
                return len((gj or {}).get("features", []) or [])
            except Exception:
                return 0

        gairmet_counts = {
            "tango": _feat_count(gairmet.get("tango") if isinstance(gairmet, dict) else {}),
            "zulu": _feat_count(gairmet.get("zulu") if isinstance(gairmet, dict) else {}),
            "sierra": _feat_count(gairmet.get("sierra") if isinstance(gairmet, dict) else {}),
        }
        sigmet_count = _feat_count(sigmet)

                # TAFs (origin/destination)
        o_taf = None
        d_taf = None
        try:
            o_taf = await self.aviationweather.fetch_taf(req.origin)
            d_taf = await self.aviationweather.fetch_taf(req.destination)
        except Exception:
            missing_products.append("taf")





        # 5) Calm, honest MVP briefing
        # briefing = (
        #     f"Surface conditions snapshot for {req.origin} -> {req.destination} (cruise FL{req.cruise_fl}). "
        #     f"Route distance ~{route.distance_nm:.0f} NM.\n\n"
        #     f"Note: METARs describe weather near the ground (most relevant to takeoff/landing). "
        #     f"Cruise conditions aloft will be covered by PIREPs/SIGMETs/G-AIRMETs in a later MVP step."
        # )

        # --- helper: find flight category for a given station in our METAR rows ---
        def _metar_cat_for_station(station: str, rows: list[dict]) -> str | None:
            st = (station or "").upper().strip()
            for r in rows or []:
                sid = (r.get("icaoId") or r.get("stationId") or r.get("id") or "").upper().strip()
                if sid == st:
                    cat = r.get("flightCat") or r.get("fltCat") or r.get("flightCategory")
                    if isinstance(cat, str):
                        return cat.strip().upper()
                    return None
            return None

        origin_cat = _metar_cat_for_station(req.origin, metar_rows)
        dest_cat   = _metar_cat_for_station(req.destination, metar_rows)

        summary = {
            "origin": req.origin,
            "destination": req.destination,
            "cruise_fl": req.cruise_fl,
            "distance_nm": round(route.distance_nm, 1),
            "corridor_nm_each_side": 50,
            "metar_stations_requested": metar_stations,
            "metars_returned": len(metar_rows),
            "missing_products": missing_products,

            "pireps_returned": len(pirep_rows),
            "pirep_counts": pirep_counts,

            "gairmet_counts": gairmet_counts,
            "sigmet_count": sigmet_count,

            "tafs_returned": int(bool(o_taf)) + int(bool(d_taf)),

            "products": {
                "metar": "ok" if "metar" not in missing_products else "failed",
                "taf": "ok" if "taf" not in missing_products else "failed",
                "pirep": "ok" if "pirep" not in missing_products else "failed",
                "sigmet": "ok" if "sigmet" not in missing_products else "failed",
                "gairmet": "ok" if "gairmet" not in missing_products else "failed",
            },
        }

        # LLM/fallback briefing AFTER summary dict is closed
        from app.services.briefing_service import BriefingService, BriefingInputs

        briefing = BriefingService().generate(
            BriefingInputs(
                origin=req.origin,
                destination=req.destination,
                cruise_fl=int(req.cruise_fl),
                calm=bool(req.calm),

                origin_metar_cat=origin_cat,
                dest_metar_cat=dest_cat,

                origin_metar_raw=None,  # optional; we can wire this later if you want
                dest_metar_raw=None,

                origin_taf_raw=(o_taf or {}).get("raw"),
                dest_taf_raw=(d_taf or {}).get("raw"),

                pirep_counts=pirep_counts,
                sigmet_count=sigmet_count,
                gairmet_counts=gairmet_counts,
            )
        )

        # 4) Build map (route + corridor + metar markers)
        html = self.map_service.build(
            route,
            metar_rows=metar_rows,
            pirep_rows=pirep_rows,
            gairmet=gairmet,
            sigmet=sigmet,
            calm=req.calm,
            origin_taf=o_taf,
            dest_taf=d_taf,
            briefing=briefing,
            embed=req.embed,
        )


        self.map_store.save_html(map_id, html)




        return ForecastResponse(
            id=map_id,
            briefing=briefing,
            summary=summary,
            map_url=f"/maps/{map_id}.html",
        )
