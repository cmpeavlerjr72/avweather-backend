from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from app.api.deps import rate_limit
from app.services.briefing_service import BriefingService

router = APIRouter()


class InterpretRequest(BaseModel):
    type: str = Field(..., description="metar or pirep")
    text: str = Field(..., description="Raw METAR/PIREP text")
    station: str | None = Field(None, description="ICAO station (optional, METAR)")
    fl: str | int | None = Field(None, description="Flight level/altitude (optional, PIREP)")


class InterpretResponse(BaseModel):
    plain: str


@router.post("/interpret", response_model=InterpretResponse)
async def post_interpret(
    payload: InterpretRequest,
    request: Request,
    _=Depends(rate_limit),
):

    t = (payload.type or "").strip().lower()
    raw = (payload.text or "").strip()
    if t not in ("metar", "pirep"):
        raise HTTPException(status_code=400, detail="type must be 'metar' or 'pirep'")
    if not raw:
        raise HTTPException(status_code=400, detail="text is required")

    try:
        bs = BriefingService()

        tier = request.headers.get("X-BB-Tier", "free")
        bs.set_tier(tier)

        if t == "metar":
            plain = bs.interpret_metar(raw, station=payload.station)
        else:
            plain = bs.interpret_pirep(raw, fl=payload.fl)

        return InterpretResponse(plain=plain or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Interpretation timed out. Please try again.")
    except Exception as e:
        # keep it safe but useful
        raise HTTPException(status_code=500, detail=f"Interpretation failed: {type(e).__name__}")

