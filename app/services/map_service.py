from __future__ import annotations

from typing import Any, List, Tuple
import folium
import html as _html

from app.data.airports_repo import airports_repo


def _as_paragraphs(text: str) -> str:
    """Convert blank-line separated text into <p> blocks, HTML-escaped."""
    if not text:
        return ""
    safe = _html.escape(text.strip())
    parts = [p.strip() for p in safe.split("\n\n") if p.strip()]
    return "<p>" + "</p><p>".join(parts) + "</p>"


def _sanitize_featurecollection(gj: dict | None) -> dict:
    """Return a safe FeatureCollection shape for Folium."""
    if not isinstance(gj, dict) or gj.get("type") != "FeatureCollection":
        return {"type": "FeatureCollection", "features": []}
    feats = gj.get("features")
    if not isinstance(feats, list):
        return {"type": "FeatureCollection", "features": []}
    # drop invalid features
    safe_feats = [f for f in feats if isinstance(f, dict)]
    return {"type": "FeatureCollection", "features": safe_feats}


def _ensure_prop(gj: dict | None, key: str, default: str) -> dict:
    """
    Folium GeoJsonTooltip asserts requested fields exist in feature properties.
    Ensure every feature has properties[key] as a non-empty string.
    """
    gj = _sanitize_featurecollection(gj)

    for feat in gj["features"]:
        props = feat.get("properties")
        if not isinstance(props, dict):
            props = {}
            feat["properties"] = props

        if props.get(key) in (None, ""):
            props[key] = props.get("hazard") or props.get("phenomenon") or props.get("type") or default

    return gj


def _safe_tooltip(gj: dict, preferred_fields: list[str], aliases: list[str] | None = None):
    """
    Build a GeoJsonTooltip only using fields that exist in ALL features.
    Returns None if no safe fields exist.
    """
    feats = gj.get("features") if isinstance(gj, dict) else None
    if not isinstance(feats, list) or not feats:
        return None

    common: set[str] | None = None
    for f in feats:
        props = f.get("properties") if isinstance(f, dict) else None
        if not isinstance(props, dict):
            props = {}
        kset = set(props.keys())
        common = kset if common is None else (common & kset)

    if not common:
        return None

    fields = [f for f in preferred_fields if f in common]
    if not fields:
        return None

    if aliases and len(aliases) == len(preferred_fields):
        # Map alias list to only the kept fields
        alias_map = dict(zip(preferred_fields, aliases))
        kept_aliases = [alias_map[f] for f in fields]
    else:
        kept_aliases = None

    return folium.GeoJsonTooltip(fields=fields, aliases=kept_aliases, sticky=False)


class MapService:
    """
    Builds an interactive Folium HTML map for the route corridor.
    Includes METAR markers (surface) + PIREPs (aloft) + SIGMET/G-AIRMET polygons.
    """

    def build(
        self,
        route: Any,
        metar_rows: list[dict] | None = None,
        pirep_rows: list[dict] | None = None,
        gairmet: dict | None = None,
        sigmet: dict | None = None,
        calm: bool = False,
        origin_taf: dict | None = None,
        dest_taf: dict | None = None,
        briefing: str | None = None,
        embed: bool = False,
    ) -> str:

        def _mk_airport_popup(title: str, metar_raw: str | None, taf_raw: str | None) -> str:
            parts = [f"<b>{title}</b>"]
            if metar_raw:
                parts.append("<b>METAR</b>")
                parts.append(f"<pre style='white-space:pre-wrap'>{metar_raw}</pre>")
            if taf_raw:
                parts.append("<b>TAF</b>")
                parts.append(f"<pre style='white-space:pre-wrap'>{taf_raw}</pre>")
            return "<br>".join(parts)

        def _metar_raw_for_station(rows: list[dict], station_icao: str) -> str | None:
            station_icao = (station_icao or "").upper().strip()
            for r in rows:
                icao = (r.get("icaoId") or r.get("stationId") or "").upper().strip()
                if icao != station_icao:
                    continue
                return (
                    r.get("rawOb")
                    or r.get("rawObs")
                    or r.get("rawText")
                    or r.get("raw")
                    or ""
                ) or None
            return None

        metar_rows = metar_rows or []
        pirep_rows = pirep_rows or []

        origin_metar_raw = _metar_raw_for_station(metar_rows, route.origin.icao)
        dest_metar_raw = _metar_raw_for_station(metar_rows, route.destination.icao)

        origin_taf_raw = (origin_taf or {}).get("raw") if isinstance(origin_taf, dict) else None
        dest_taf_raw = (dest_taf or {}).get("raw") if isinstance(dest_taf, dict) else None

        points: List[Tuple[float, float]] = route.route_points
        mid = points[len(points) // 2]
        m = folium.Map(location=[mid[0], mid[1]], zoom_start=5, control_scale=True)

        # Briefing overlay
        if briefing and not embed:
            briefing_html = _as_paragraphs(briefing)
            panel = f"""
            <div style="
                position: fixed; top: 14px; left: 14px; z-index: 10000;
                background: rgba(255,255,255,0.97); padding: 12px 14px; border-radius: 10px;
                box-shadow: 0 4px 16px rgba(0,0,0,.25);
                font: 13px/1.45 system-ui,-apple-system,'Segoe UI',Roboto,Arial;">
              <div style="font-weight:600; margin-bottom:6px;">
                Captain-style Briefing (not the operating crew)
              </div>
              <div style="max-width: 460px; max-height: 260px; overflow:auto;">
                {briefing_html}
              </div>
            </div>
            """
            m.get_root().html.add_child(folium.Element(panel))

        # Corridor polygon
        folium.GeoJson(
            data=route.corridor_polygon_geojson,
            name="Route Corridor",
            tooltip="Corridor (surface context)",
            style_function=lambda _: {
                "fillColor": "#1f77b4",
                "color": "#1f77b4",
                "weight": 2,
                "fillOpacity": 0.12,
            },
        ).add_to(m)

        # Great-circle route line
        folium.PolyLine(
            locations=[(lat, lon) for (lat, lon) in points],
            weight=4,
            opacity=0.9,
            tooltip="Great-circle route",
        ).add_to(m)

        # Origin/Destination markers
        folium.Marker(
            location=[route.origin.lat, route.origin.lon],
            tooltip=f"Origin: {route.origin.icao}",
            popup=folium.Popup(
                _mk_airport_popup(
                    f"{route.origin.icao} — {route.origin.name}",
                    origin_metar_raw,
                    origin_taf_raw,
                ),
                max_width=520,
            ),
            icon=folium.Icon(color="green"),
        ).add_to(m)

        folium.Marker(
            location=[route.destination.lat, route.destination.lon],
            tooltip=f"Destination: {route.destination.icao}",
            popup=folium.Popup(
                _mk_airport_popup(
                    f"{route.destination.icao} — {route.destination.name}",
                    dest_metar_raw,
                    dest_taf_raw,
                ),
                max_width=520,
            ),
            icon=folium.Icon(color="red"),
        ).add_to(m)

        # METAR layer
        def cat_color(cat: str | None) -> str:
            cat = (cat or "").upper()
            if cat == "VFR":
                return "green"
            if cat == "MVFR":
                return "blue"
            if cat == "IFR":
                return "red"
            if cat == "LIFR":
                return "purple"
            return "gray"

        metar_layer = folium.FeatureGroup(name="METAR (surface)", show=True)
        for row in metar_rows:
            lat = row.get("lat")
            lon = row.get("lon")
            if lat is None or lon is None:
                continue

            icao = (row.get("icaoId") or row.get("stationId") or "").upper()
            raw = row.get("rawOb") or row.get("rawObs") or row.get("rawText") or ""
            cat = row.get("flightCat") or row.get("fltCat") or row.get("flightCategory")
            cat = cat.strip().upper() if isinstance(cat, str) else None

            color = cat_color(cat)
            popup_html = (
                f"<b>{icao}</b> "
                f"<span style='padding:2px 6px;border-radius:10px;background:{color};color:white;'>"
                f"{(cat or 'UNK')}</span>"
                f"<br><pre style='white-space:pre-wrap;margin-top:6px;'>{raw}</pre>"
            )

            folium.CircleMarker(
                location=[lat, lon],
                radius=6,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.85,
                tooltip=f"{icao} METAR ({cat or 'UNK'})",
                popup=popup_html,
            ).add_to(metar_layer)

        metar_layer.add_to(m)

        # PIREP layer
        def pirep_intensity(p: dict) -> str | None:
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

        def pirep_color(level: str | None) -> str:
            if level == "SEV":
                return "red"
            if level == "MOD":
                return "orange"
            if level == "LGT":
                return "lightblue"
            return "gray"

        pirep_layer = folium.FeatureGroup(name="PIREPs (aloft)", show=True)
        for p in pirep_rows:
            lat = p.get("lat")
            lon = p.get("lon")
            if lat is None or lon is None:
                continue

            lvl = pirep_intensity(p)
            color = pirep_color(lvl)

            fl = p.get("fltLvl") or ""
            tb1 = (p.get("tbInt1") or "")
            tb2 = (p.get("tbInt2") or "")
            ic1 = (p.get("icgInt1") or "")
            ic2 = (p.get("icgInt2") or "")
            raw = p.get("rawOb") or p.get("raw") or ""

            popup = (
                f"<b>PIREP</b> "
                f"<span style='padding:2px 6px;border-radius:10px;background:{color};color:white;'>"
                f"{(lvl or 'UNK')}</span>"
                f"<br>FL: {fl}"
                f"<br>TB: {tb1} {tb2} | ICE: {ic1} {ic2}"
                f"<br><pre style='white-space:pre-wrap;margin-top:6px;'>{raw}</pre>"
            )

            folium.CircleMarker(
                location=[lat, lon],
                radius=5,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.85,
                tooltip=f"PIREP ({lvl or 'UNK'}) {fl}",
                popup=popup,
            ).add_to(pirep_layer)

        pirep_layer.add_to(m)

        # Advisories (SIGMET / G-AIRMET)
        gairmet = gairmet if isinstance(gairmet, dict) else {}
        sigmet = sigmet if isinstance(sigmet, dict) else {"type": "FeatureCollection", "features": []}

        def _hazard_color(props: dict) -> str:
            hz = (props.get("hazard") or props.get("type") or props.get("phenom") or "").lower()
            if "conv" in hz or "ts" in hz:
                return "red"
            if "turb" in hz or "llws" in hz:
                return "orange"
            if "ice" in hz or "fzlvl" in hz:
                return "blue"
            if "ifr" in hz or "mtn" in hz:
                return "gray"
            return "purple"

        def _style(feat):
            props = (feat or {}).get("properties", {}) or {}
            if not isinstance(props, dict):
                props = {}
            c = _hazard_color(props)
            return {"color": c, "weight": 2, "fillOpacity": 0.12}

        # SIGMET layer (sanitize + safe tooltip)
        sigmet = _ensure_prop(sigmet, "hazard", "SIGMET")
        sigmet_tooltip = _safe_tooltip(sigmet, ["hazard"], aliases=["Hazard"])
        folium.GeoJson(
            data=sigmet,
            name="SIGMETs",
            style_function=_style,
            tooltip=sigmet_tooltip,
            show=(not calm),
        ).add_to(m)

        # G-AIRMET layers (sanitize + safe tooltip)
        for key, label in [
            ("tango", "G-AIRMET (Tango - Turb)"),
            ("zulu", "G-AIRMET (Zulu - Icing)"),
            ("sierra", "G-AIRMET (Sierra - IFR/Mtn)"),
        ]:
            gj = gairmet.get(key)
            if not gj:
                continue

            gj = _ensure_prop(gj, "hazard", "G-AIRMET")
            gj_tooltip = _safe_tooltip(gj, ["hazard"], aliases=["Hazard"])

            folium.GeoJson(
                data=gj,
                name=label,
                style_function=_style,
                tooltip=gj_tooltip,
                show=(not calm),
            ).add_to(m)

        # Fit to corridor bbox
        min_lon, min_lat, max_lon, max_lat = route.corridor_bbox
        m.fit_bounds([[min_lat, min_lon], [max_lat, max_lon]])

        folium.LayerControl(collapsed=True).add_to(m)
        return m.get_root().render()
