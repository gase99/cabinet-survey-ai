from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator
from typing import Optional

class Settings(BaseSettings):
    app_name: str = "Cabinet Survey AI"
    app_env: str = "development"
    app_version: str = "0.1.0"
    api_prefix: str = "/api/v1"

    database_url: str = "sqlite:///./cabinet_survey_dev.db"
    # For tests override to sqlite memory
    jwt_secret: str = "replace-with-a-long-random-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    ai_provider: str = "disabled"
    ai_api_key: str | None = None
    ai_model: str | None = None
    ai_base_url: str | None = None

    telegram_bot_token: str | None = None
    telegram_webhook_secret: str | None = None
    telegram_webhook_url: str | None = None

    upload_max_bytes: int = 15 * 1024 * 1024
    upload_allowed_types: str = "image/jpeg,image/png,image/webp,application/pdf"
    rate_limit_auth_per_minute: int = 10
    rate_limit_ai_per_minute: int = 20

    cors_origins: str = "http://localhost:3000,http://localhost:5173,http://localhost:8080"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_file_encoding="utf-8")

    @model_validator(mode="after")
    def production_secrets(self):
        if self.app_env == "production":
            if len(self.jwt_secret) < 32 or "replace-with" in self.jwt_secret or "change-me" in self.jwt_secret:
                raise ValueError("Production JWT_SECRET must be an explicit high-entropy secret of at least 32 characters")
            if not self.database_url.startswith("postgresql"):
                raise ValueError("Production requires PostgreSQL")
            if "*" in self.cors_origin_list:
                raise ValueError("Production CORS must use explicit origins")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")

settings = Settings()
