from __future__ import annotations
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).parent / ".env"


class Settings(BaseSettings):
    # MDH
    mdh_base_url: str = "http://localhost:8080/api/v1"
    mdh_api_key: str = ""
    mdh_enabled: bool = True          # False → yfinance fallback
    mdh_lake_root: str = str(Path(__file__).resolve().parents[2] / "market_data_hub" / "data" / "lake")  # lectura directa (sin HTTP) para flujos no-Price-Action

    # App
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Persistencia de análisis (objeto Edge: edge.json + return_samples.parquet)
    storage_root: str = "./data"

    model_config = SettingsConfigDict(
        env_prefix="EE_",
        env_file=str(_ENV_FILE),
        extra="ignore",
    )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
