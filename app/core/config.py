from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-5"

    # App
    app_name: str = Field(default="AvWeather Backend")
    env: str = Field(default="development")
    log_level: str = Field(default="INFO")

    # Network safety
    http_timeout_seconds: float = Field(default=12.0)
    max_request_seconds: float = Field(default=25.0)

    # Rate limiting (MVP, per instance)
    rate_limit_per_minute: int = Field(default=30)

    # Caching (we’ll use later when we add aviationweather.gov client)
    cache_ttl_seconds: int = Field(default=120)

    # Ephemeral map storage (Render-friendly)
    maps_dir: str = Field(default="/tmp/avweather_maps")
    map_ttl_seconds: int = Field(default=3600)

    # OpenAI (server-side only)
    openai_api_key: Optional[str] = None
    openai_model: str = Field(default="gpt-4o-mini")
    openai_timeout_seconds: float = Field(default=10.0)

settings = Settings()
