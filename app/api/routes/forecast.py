from fastapi import APIRouter, Depends, HTTPException, Request
from app.models.forecast import ForecastRequest, ForecastResponse
from app.api.deps import get_forecast_service, rate_limit
from app.services.forecast_service import ForecastService

router = APIRouter()

_ALLOWED_BRIEFING_VERSIONS = {"v1", "v2"}  # v1=old, v2=alt

@router.post("/forecast", response_model=ForecastResponse)
async def post_forecast(
    payload: ForecastRequest,
    request: Request,
    _=Depends(rate_limit),
    svc: ForecastService = Depends(get_forecast_service),
    briefing: str | None = None,  # <-- query param: /forecast?briefing=v2
):
    try:
        payload.tier = request.headers.get("X-BB-Tier", payload.tier or "free")

        # Option A: query param wins, fallback to header, then default v1
        header_version = request.headers.get("X-BB-Briefing")
        version = (briefing or header_version or "v1").strip().lower()

        if version not in _ALLOWED_BRIEFING_VERSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid briefing version '{version}'. Allowed: {sorted(_ALLOWED_BRIEFING_VERSIONS)}",
            )

        # IMPORTANT: this requires ForecastService.generate to accept briefing_version (next section)
        return await svc.generate(payload, briefing_version=version)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Upstream timeout. Please try again.")
