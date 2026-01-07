from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from app.api.deps import get_map_store
from app.storage.map_store import MapStore

router = APIRouter()

@router.get("/maps/{map_id}.html")
async def get_map(map_id: str, store: MapStore = Depends(get_map_store)):
    path = store.get_path(map_id)
    if not path:
        raise HTTPException(status_code=404, detail="Map not found (expired).")
    return FileResponse(path, media_type="text/html")
