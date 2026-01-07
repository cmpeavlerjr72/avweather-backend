#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
from textwrap import dedent

ROOT = Path.cwd()

DIRS = [
    "app",
    "app/core",
    "app/api",
    "app/api/routes",
    "app/models",
    "app/services",
    "app/clients",
    "app/storage",
    "app/utils",
    "tests",
]

FILES: dict[str, str] = {
    # --- app ---
    "app/__init__.py": "",
    "app/main.py": dedent("""\
        # FastAPI app entrypoint
        # You will paste the full scaffold code here.
    """),
    # --- core ---
    "app/core/__init__.py": "",
    "app/core/config.py": dedent("""\
        # Pydantic Settings live here
        # You will paste the full config code here.
    """),
    "app/core/logging.py": dedent("""\
        # Logging configuration utilities (optional for MVP)
    """),
    "app/core/errors.py": dedent("""\
        # Custom exception types and HTTP mapping utilities (optional for MVP)
    """),
    # --- api ---
    "app/api/__init__.py": "",
    "app/api/deps.py": dedent("""\
        # Dependency injection + rate limiting utilities live here
        # You will paste the full deps scaffold here.
    """),
    "app/api/routes/__init__.py": "",
    "app/api/routes/forecast.py": dedent("""\
        # POST /api/forecast route lives here
        # You will paste the full router scaffold here.
    """),
    "app/api/routes/maps.py": dedent("""\
        # GET /maps/{id}.html route lives here
        # You will paste the full router scaffold here.
    """),
    # --- models ---
    "app/models/__init__.py": "",
    "app/models/forecast.py": dedent("""\
        # Pydantic request/response models live here
        # You will paste the full models scaffold here.
    """),
    # --- services ---
    "app/services/__init__.py": "",
    "app/services/forecast_service.py": dedent("""\
        # Forecast orchestration service lives here
        # You will paste the full service scaffold here.
    """),
    "app/services/route_service.py": dedent("""\
        # Great-circle route + corridor geometry logic lives here
    """),
    "app/services/map_service.py": dedent("""\
        # Folium map builder logic lives here
    """),
    "app/services/briefing_service.py": dedent("""\
        # OpenAI briefing generator + fallback lives here
    """),
    # --- clients ---
    "app/clients/__init__.py": "",
    "app/clients/aviationweather.py": dedent("""\
        # aviationweather.gov client functions live here
    """),
    "app/clients/openai_client.py": dedent("""\
        # OpenAI client wrapper (server-side only) lives here
    """),
    # --- storage ---
    "app/storage/__init__.py": "",
    "app/storage/map_store.py": dedent("""\
        # Ephemeral HTML map storage (save + TTL cleanup) lives here
        # You will paste the full map store scaffold here.
    """),
    # --- utils ---
    "app/utils/__init__.py": "",
    "app/utils/ids.py": dedent("""\
        import secrets

        def new_id(nbytes: int = 12) -> str:
            \"\"\"URL-safe id for map files.\"\"\"
            return secrets.token_urlsafe(nbytes)
    """),
    "app/utils/time.py": dedent("""\
        # Time helpers live here (optional)
    """),
    "app/utils/geo.py": dedent("""\
        # Geo helpers (haversine, bearings, etc.) live here (optional)
    """),
    "app/utils/cache.py": dedent("""\
        # Simple in-memory TTL cache lives here
        # You will paste the full TTLCache scaffold here.
    """),
    # --- tests ---
    "tests/test_health.py": dedent("""\
        def test_placeholder():
            assert True
    """),
    "tests/test_forecast_contract.py": dedent("""\
        def test_placeholder():
            assert True
    """),

    # --- root files ---
    ".env.example": dedent("""\
        # Copy to .env for local development (never commit .env)
        ENV=development
        LOG_LEVEL=INFO

        # OpenAI (server-side only)
        OPENAI_API_KEY=replace_me
        OPENAI_MODEL=gpt-4o-mini
        OPENAI_TIMEOUT_SECONDS=10

        # Network/timeouts
        HTTP_TIMEOUT_SECONDS=12
        MAX_REQUEST_SECONDS=25

        # Rate limiting + caching
        RATE_LIMIT_PER_MINUTE=30
        CACHE_TTL_SECONDS=120

        # Ephemeral map storage
        MAPS_DIR=/tmp/avweather_maps
        MAP_TTL_SECONDS=3600
    """),
    ".gitignore": dedent("""\
        .env
        __pycache__/
        *.pyc
        .pytest_cache/
        .mypy_cache/
        .ruff_cache/
        .venv/
        venv/
        dist/
        build/
        *.log
        /tmp/
    """),
    "requirements.txt": dedent("""\
        fastapi==0.115.0
        uvicorn[standard]==0.30.6
        pydantic-settings==2.4.0
        httpx==0.27.2
        folium==0.17.0
    """),
    "README.md": dedent("""\
        # AvWeather Backend (MVP)

        FastAPI backend for route corridor weather + passenger-friendly briefing.

        ## Local dev
        ```bash
        python -m venv .venv
        # Windows: .venv\\Scripts\\activate
        # macOS/Linux: source .venv/bin/activate
        pip install -r requirements.txt

        cp .env.example .env
        uvicorn app.main:app --reload
        ```

        ## Endpoints
        - POST /api/forecast
        - GET /maps/{id}.html
        - GET /healthz
    """),
}

def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)

def write_file(path: Path, content: str) -> None:
    if path.exists():
        return
    path.write_text(content, encoding="utf-8")

def main() -> None:
    print(f"[bootstrap] creating structure in: {ROOT}")

    for d in DIRS:
        ensure_dir(ROOT / d)

    for rel, content in FILES.items():
        p = ROOT / rel
        ensure_dir(p.parent)
        write_file(p, content)

    print("[bootstrap] done.")
    print("\nNext steps:")
    print("1) Create and activate a venv")
    print("2) pip install -r requirements.txt")
    print("3) Paste the scaffold code into app/main.py, app/core/config.py, etc.")
    print("4) Run: uvicorn app.main:app --reload")

if __name__ == "__main__":
    main()
