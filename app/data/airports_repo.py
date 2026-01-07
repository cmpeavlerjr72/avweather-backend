from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DATA_PATH = Path(__file__).resolve().parent / "airports_us.csv"


@dataclass(frozen=True)
class AirportRecord:
    icao: str
    iata: str
    name: str
    lat: float
    lon: float
    elevation_ft: Optional[int]
    municipality: str
    region: str
    scheduled_service: str
    type: str


class AirportsRepo:
    def __init__(self, csv_path: Path = DATA_PATH):
        self.csv_path = csv_path
        self._by_icao: Dict[str, AirportRecord] = {}
        self._by_iata: Dict[str, AirportRecord] = {}
        self._all: List[AirportRecord] = []
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return
        if not self.csv_path.exists():
            raise FileNotFoundError(
                f"Airport dataset not found at {self.csv_path}. "
                f"Run scripts/build_us_airports_csv.py to generate it."
            )

        with self.csv_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                icao = (row.get("icao") or "").strip().upper()
                if not icao:
                    continue

                iata = (row.get("iata") or "").strip().upper()
                name = (row.get("name") or "").strip()
                lat = float(row["lat"])
                lon = float(row["lon"])

                elev_raw = (row.get("elevation_ft") or "").strip()
                elevation_ft = int(elev_raw) if elev_raw.isdigit() else None

                rec = AirportRecord(
                    icao=icao,
                    iata=iata,
                    name=name,
                    lat=lat,
                    lon=lon,
                    elevation_ft=elevation_ft,
                    municipality=(row.get("municipality") or "").strip(),
                    region=(row.get("region") or "").strip(),
                    scheduled_service=(row.get("scheduled_service") or "").strip(),
                    type=(row.get("type") or "").strip(),
                )

                self._by_icao[icao] = rec
                if iata:
                    # If duplicates exist, first wins (fine for MVP)
                    self._by_iata.setdefault(iata, rec)
                self._all.append(rec)

        self._loaded = True

    def get_by_icao(self, icao: str) -> Optional[AirportRecord]:
        self.load()
        return self._by_icao.get(icao.strip().upper())

    def get_by_iata(self, iata: str) -> Optional[AirportRecord]:
        self.load()
        return self._by_iata.get(iata.strip().upper())

    def all(self) -> List[AirportRecord]:
        self.load()
        return list(self._all)

    def search(self, q: str, limit: int = 10) -> List[Tuple[AirportRecord, int]]:
        """
        Returns list of (record, score) sorted by score desc.
        Scoring is simple but good enough for MVP autocomplete.
        """
        self.load()
        q = (q or "").strip().lower()
        if not q:
            return []

        def score(rec: AirportRecord) -> int:
            icao = rec.icao.lower()
            iata = rec.iata.lower()
            name = rec.name.lower()
            muni = rec.municipality.lower()
            region = rec.region.lower()

            # Highest: exact code match
            if q == icao or (iata and q == iata):
                return 100

            s = 0
            # Startswith on codes
            if icao.startswith(q):
                s = max(s, 90)
            if iata and iata.startswith(q):
                s = max(s, 88)

            # Contains on codes
            if q in icao:
                s = max(s, 80)
            if iata and q in iata:
                s = max(s, 78)

            # Name/municipality matches
            if name.startswith(q):
                s = max(s, 70)
            if q in name:
                s = max(s, 60)
            if muni.startswith(q):
                s = max(s, 55)
            if q in muni:
                s = max(s, 45)
            if q in region:
                s = max(s, 30)

            return s

        scored = [(rec, score(rec)) for rec in self._all]
        scored = [x for x in scored if x[1] > 0]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[: max(1, min(limit, 50))]


# singleton repo for the app
airports_repo = AirportsRepo()
