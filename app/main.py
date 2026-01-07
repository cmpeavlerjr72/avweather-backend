import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.routes.forecast import router as forecast_router
from app.api.routes.maps import router as maps_router

from app.api.routes.airports import router as airports_router


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # tighten later
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    app.include_router(forecast_router, prefix="/api", tags=["forecast"])
    app.include_router(maps_router, tags=["maps"])
    app.include_router(airports_router, prefix="/api", tags=["airports"])


    return app

app = create_app()

os.makedirs(settings.maps_dir, exist_ok=True)
