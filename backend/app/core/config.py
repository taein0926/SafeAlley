from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    postgres_db: str = Field(default="safealley")
    postgres_user: str = Field(default="safealley")
    postgres_password: str = Field(default="safealley-local-only")
    db_host: str = Field(default="database")
    db_port: int = Field(default=5432)
    db_connect_timeout_seconds: int = Field(default=5, ge=1, le=30)
    route_snap_max_distance_m: float = Field(default=500, gt=0, le=5000)
    safe_route_distance_weight: float = Field(default=1.0, gt=0, le=100)
    safe_route_risk_weight: float = Field(default=5.0, ge=0, le=100)
    safety_cctv_weight: float = Field(default=0.40, ge=0, le=1)
    safety_help_point_weight: float = Field(default=0.20, ge=0, le=1)
    ollama_base_url: str = Field(default="http://host.docker.internal:11434")
    ollama_model: str = Field(default="qwen3:4b", min_length=1)
    ollama_timeout_seconds: float = Field(default=300, gt=0, le=300)
    ollama_keep_alive: str = Field(default="10m", min_length=1)
    ollama_intent_cache_seconds: float = Field(default=300, ge=0, le=3600)
    nominatim_base_url: str = Field(default="https://nominatim.openstreetmap.org")
    nominatim_user_agent: str = Field(default="SafeAlley-MVP/0.1", min_length=1)
    nominatim_timeout_seconds: float = Field(default=10, gt=0, le=60)

    model_config = SettingsConfigDict(case_sensitive=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
