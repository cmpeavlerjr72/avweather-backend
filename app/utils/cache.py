import time
from typing import Any, Optional

class TTLCache:
    def __init__(self, default_ttl: int = 120):
        self.default_ttl = default_ttl
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        item = self._store.get(key)
        if not item:
            return None
        exp, val = item
        if time.time() > exp:
            self._store.pop(key, None)
            return None
        return val

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        ttl = self.default_ttl if ttl is None else ttl
        self._store[key] = (time.time() + ttl, value)
