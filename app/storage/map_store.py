import os
import time
from typing import Optional

class MapStore:
    def __init__(self, maps_dir: str, ttl_seconds: int):
        self.maps_dir = maps_dir
        self.ttl_seconds = ttl_seconds
        os.makedirs(self.maps_dir, exist_ok=True)

    def _path(self, map_id: str) -> str:
        return os.path.join(self.maps_dir, f"{map_id}.html")

    def save_html(self, map_id: str, html: str) -> str:
        self._cleanup()
        path = self._path(map_id)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        return path

    def get_path(self, map_id: str) -> Optional[str]:
        self._cleanup()
        path = self._path(map_id)
        if not os.path.exists(path):
            return None
        age = time.time() - os.path.getmtime(path)
        if age > self.ttl_seconds:
            try:
                os.remove(path)
            except OSError:
                pass
            return None
        return path

    def _cleanup(self) -> None:
        try:
            now = time.time()
            for name in os.listdir(self.maps_dir):
                if not name.endswith(".html"):
                    continue
                p = os.path.join(self.maps_dir, name)
                if now - os.path.getmtime(p) > self.ttl_seconds:
                    try:
                        os.remove(p)
                    except OSError:
                        pass
        except OSError:
            pass
