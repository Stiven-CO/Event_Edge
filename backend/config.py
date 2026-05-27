from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # MDH
    mdh_base_url: str = "http://localhost:8000/api/v1"
    mdh_api_key: str = ""
    mdh_enabled: bool = True          # False → yfinance fallback

    # MT5
    mt5_login: int = 0
    mt5_password: str = ""            # nunca en logs ni en respuestas API
    mt5_server: str = ""

    # TWS
    tws_api_key: str = ""             # vacío → 403 en endpoints TWS

    # App
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    model_config = SettingsConfigDict(
        env_prefix="EE_",
        env_file=".env",
        extra="ignore",
    )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
