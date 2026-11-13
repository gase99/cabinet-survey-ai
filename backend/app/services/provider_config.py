"""Server-side provider credentials. Encryption master key is never in the database."""
from cryptography.fernet import Fernet, InvalidToken
from app.core.config import settings
from app.models.db_models import AIConfig, AIUsageLog
from datetime import datetime, timezone
from app.ai.provider import AIUnavailableError, get_ai_provider


def cipher():
    if not settings.secret_encryption_key:
        raise AIUnavailableError('SECRET_ENCRYPTION_KEY is required for stored provider credentials')
    try:
        return Fernet(settings.secret_encryption_key.encode())
    except (ValueError,TypeError):
        raise AIUnavailableError('Invalid secret encryption configuration')


def encrypt_key(value):
    return cipher().encrypt(value.encode()).decode()


def configured_provider(db):
    config=db.query(AIConfig).filter_by(provider=settings.ai_provider).with_for_update().first()
    provider=get_ai_provider(settings.ai_provider)
    if config:
        if not config.enabled:
            raise AIUnavailableError('Selected AI provider is disabled by administrator')
        if config.usage_limit_per_day is not None:
            start=datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0)
            requests=db.query(AIUsageLog).filter(AIUsageLog.provider==config.provider, AIUsageLog.created_at>=start).count()
            if requests>=config.usage_limit_per_day:
                raise AIUnavailableError('Provider daily request limit reached')
        if settings.ai_provider=='openai_compatible':
            if config.api_key_encrypted:
                try:
                    provider.api_key=cipher().decrypt(config.api_key_encrypted.encode()).decode()
                except (InvalidToken,ValueError):
                    raise AIUnavailableError('Stored provider credential cannot be decrypted')
            if config.model:
                provider.model=config.model
    return provider
