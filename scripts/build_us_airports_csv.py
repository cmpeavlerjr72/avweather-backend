#!/usr/bin/env python3
from __future__ import annotations

import csv
import sys
from pathlib import Path
import httpx

OURAIRPORTS_AIRPORTS_CSV = "https://davidmegginson.github.io/ourairports-data/airports.csv"

OUT_PATH = Path("app/data/airports_us.csv")

# Output columns we keep (small + useful)
OUT_FIELDS = [
    "icao",               # preferred: gps_code, else ident
    "iata",
    "name",
    "lat",
    "lon",
    "elevation_ft",
    "municipality",
    "region",
    "scheduled_service",
    "type",
]

def pick_icao(row: dict) -> str:
    """
    OurAirports rows have:
      - ident: always present (can be '00AK', 'KATL', etc.)
      - gps_code: usually ICAO (often Kxxx in US) for many airports
    For US airports, we prefer gps_code when present; else ident.
    """
    gps = (row.get("gps_code") or "").strip().upper()
    ident = (row.get("ident") or "").strip().upper()
    if gps:
        return gps
    return ident

def safe_float(s: str) -> str:
    s = (s or "").strip()
    return s

def main() -> int:
    print(f"[download] {OURAIRPORTS_AIRPORTS_CSV}")
    r = httpx.get(OURAIRPORTS_AIRPORTS_CSV, timeout=30.0)
    r.raise_for_status()
    text = r.text

    # Parse CSV from text
    reader = csv.DictReader(text.splitlines())
    us_rows = []
    seen = set()

    for row in reader:
        if (row.get("iso_country") or "").strip().upper() != "US":
            continue

        lat = (row.get("latitude_deg") or "").strip()
        lon = (row.get("longitude_deg") or "").strip()
        if not lat or not lon:
            continue

        icao = pick_icao(row)
        if not icao:
            continue

        # Avoid duplicates (some rows can collide between ident/gps_code)
        key = icao
        if key in seen:
            continue
        seen.add(key)

        us_rows.append({
            "icao": icao,
            "iata": ((row.get("iata_code") or "").strip().upper()),
            "name": (row.get("name") or "").strip(),
            "lat": safe_float(lat),
            "lon": safe_float(lon),
            "elevation_ft": (row.get("elevation_ft") or "").strip(),
            "municipality": (row.get("municipality") or "").strip(),
            "region": (row.get("iso_region") or "").strip(),  # e.g. US-GA
            "scheduled_service": (row.get("scheduled_service") or "").strip(),  # yes/no
            "type": (row.get("type") or "").strip(),  # large/medium/small/heliport/etc
        })

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUT_FIELDS)
        writer.writeheader()
        writer.writerows(us_rows)

    print(f"[ok] wrote {len(us_rows):,} airports -> {OUT_PATH.as_posix()}")
    print("[tip] commit app/data/airports_us.csv to your repo so Render builds do not need network.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
