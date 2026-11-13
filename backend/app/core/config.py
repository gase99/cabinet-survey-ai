from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Cabinet Survey AI"
    app_env: str = "development"
    database_url: str = "sqlite:///./cabinet_survey_dev.db"
    ai_provider: str = "disabled"
    ai_api_key: str | None = None
    telegram_bot_token: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
