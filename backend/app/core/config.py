
import ipaddress
from urllib.parse import parse_qs, urlsplit

from cryptography.fernet import Fernet
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

KNOWN_ENVIRONMENTS = frozenset({"development", "test", "production"})
_PLACEHOLDERS = ("change_me", "change-me", "changeme", "replace-with", "replace_me", "your-", "example")
_WEAK_DB_PASSWORDS = frozenset({"", "postgres", "password", "cabinet", "secret", "admin", "root", "fixture"})
_TLS_SSLMODES = frozenset({"require", "verify-ca", "verify-full"})
MIN_SECRET_LENGTH = 32


def _is_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in _PLACEHOLDERS)


def _weak_secret(value: str | None) -> bool:
    return not value or len(value) < MIN_SECRET_LENGTH or _is_placeholder(value)


def _internal_host(host: str) -> bool:
    """Loopback, a Unix socket, or a single-label service name on a private container network."""
    if not host or host.startswith("/") or host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return "." not in host


def database_url_problems(url: str) -> list[str]:
    if not url.startswith("postgresql"):
        return ["DATABASE_URL must use PostgreSQL in production"]
    parts = urlsplit(url)
    problems = []
    password = parts.password or ""
    if password.lower() in _WEAK_DB_PASSWORDS or _is_placeholder(password) or len(password) < 16:
        problems.append("DATABASE_URL password is empty, default or shorter than 16 characters")
    host = parts.hostname or ""
    sslmode = (parse_qs(parts.query).get("sslmode") or [""])[-1].lower()
    if sslmode in {"disable", "allow", "prefer"} and not _internal_host(host):
        problems.append(f"DATABASE_URL sslmode={sslmode} is insecure for a remote database host")
    elif not _internal_host(host) and sslmode not in _TLS_SSLMODES:
        problems.append("DATABASE_URL for a remote database host requires sslmode=require, verify-ca or verify-full")
    return problems


def production_problems(config: "Settings") -> list[str]:
    """Every reason the configuration is unsafe for production (empty list when safe)."""
    problems = []
    if _weak_secret(config.jwt_secret):
        problems.append(f"JWT_SECRET must be an explicit high-entropy secret of at least {MIN_SECRET_LENGTH} characters")
    if _weak_secret(config.telegram_worker_secret):
        problems.append(f"TELEGRAM_WORKER_SECRET must be set to a random secret of at least {MIN_SECRET_LENGTH} characters")
    elif config.telegram_worker_secret == config.jwt_secret:
        problems.append("TELEGRAM_WORKER_SECRET must differ from JWT_SECRET")
    if config.secret_encryption_key:
        try:
            Fernet(config.secret_encryption_key.encode())
        except (ValueError, TypeError):
            problems.append("SECRET_ENCRYPTION_KEY is not a valid Fernet key (leave empty to disable stored provider keys)")
    if config.ai_api_key and _is_placeholder(config.ai_api_key):
        problems.append("AI_API_KEY is a placeholder value")
    elif config.ai_provider != "disabled" and not config.ai_api_key and not config.secret_encryption_key:
        # The key may instead be stored encrypted by an administrator (needs the master key).
        problems.append("AI_PROVIDER is enabled but neither AI_API_KEY nor SECRET_ENCRYPTION_KEY is set")
    if config.stt_provider != "disabled" and _weak_secret_or_empty(config.stt_api_key):
        problems.append("STT_API_KEY is empty or a placeholder while STT_PROVIDER is enabled")
    problems.extend(database_url_problems(config.database_url))
    if config.debug:
        problems.append("DEBUG must be false")
    origins = [origin.strip() for origin in config.cors_allowed_origins.split(",") if origin.strip()]
    if any("*" in origin or origin.lower() == "null" for origin in origins):
        problems.append("CORS_ALLOWED_ORIGINS must list explicit origins, not a wildcard")
    if any(origin.lower().startswith("http://") for origin in origins):
        problems.append("CORS_ALLOWED_ORIGINS must use https:// origins")
    if "*" in config.forwarded_allow_ips:
        problems.append("FORWARDED_ALLOW_IPS must list the trusted gateway address(es), not '*'")
    return problems


def _weak_secret_or_empty(value: str | None) -> bool:
    return not value or _is_placeholder(value)


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

    secret_encryption_key: str | None = None
    ai_provider: str = "disabled"
    ai_api_key: str | None = None
    ai_model: str | None = None
    ai_base_url: str | None = None

    # Shared API/worker credential; NOT Telegram's webhook header secret.
    telegram_worker_secret: str | None = None

    # Provider-independent speech recognition; disabled unless explicitly configured.
    stt_provider: str = "disabled"
    stt_base_url: str | None = None
    stt_api_key: str | None = None
    stt_model: str | None = "whisper-1"
    audio_max_bytes: int = 10 * 1024 * 1024

    # Image uploads: JPEG/PNG/WebP only (magic bytes), re-encoded server-side.
    upload_max_bytes: int = 15 * 1024 * 1024
    upload_max_dimension: int = 8192
    upload_max_pixels: int = 40_000_000
    rate_limit_auth_per_minute: int = 10
    rate_limit_ai_per_minute: int = 20
    idempotency_ttl_seconds: int = 86400


    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_file_encoding="utf-8")

    # Runtime flags validated below. Android needs no CORS; only explicit origins allowed.
    debug: bool = False
    cors_allowed_origins: str = ""
    # Same variable uvicorn reads for X-Forwarded-For trust; validated, never "*".
    forwarded_allow_ips: str = "127.0.0.1"

    @model_validator(mode="after")
    def production_secrets(self):
        if self.app_env not in KNOWN_ENVIRONMENTS:
            # A typo such as "prod" must not silently skip production validation.
            raise ValueError(f"APP_ENV must be one of {sorted(KNOWN_ENVIRONMENTS)}")
        if self.app_env == "production":
            problems = production_problems(self)
            if problems:
                raise ValueError("Refusing to start in production: " + "; ".join(problems))
        return self

    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")

settings = Settings()
