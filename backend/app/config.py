from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    secret_key: str = "dev-secret-key-change-in-production"
    database_url: str = "sqlite+aiosqlite:///./trading.db"
    redis_url: str = "redis://localhost:6379"
    polygon_api_key: Optional[str] = None
    binance_api_key: Optional[str] = None
    binance_secret_key: Optional[str] = None
    oanda_api_key: Optional[str] = None
    tradingview_webhook_secret: Optional[str] = None
    expo_push_token_base_url: str = "https://exp.host/--/api/v2/push/send"
    environment: str = "development"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    class Config:
        env_file = ".env"


settings = Settings()
