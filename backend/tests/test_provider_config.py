from cryptography.fernet import Fernet
from app.core.config import settings
from app.models.db_models import User,AIConfig
from app.services.provider_config import configured_provider


def test_admin_keys_are_encrypted_and_used_without_leaking(client,auth_headers,db_session,monkeypatch):
    db_session.query(User).filter_by(email='test@example.com').one().role='admin'
    db_session.commit()
    payload={'provider':'openai_compatible','api_key':'fixture-only-provider-key','model':'vision-fixture'}
    monkeypatch.setattr(settings,'secret_encryption_key',None)
    assert client.put('/api/v1/admin/ai-config',headers=auth_headers,json=payload).status_code==503
    assert db_session.query(AIConfig).count()==0
    key=Fernet.generate_key().decode()
    monkeypatch.setattr(settings,'secret_encryption_key',key)
    assert client.put('/api/v1/admin/ai-config',headers=auth_headers,json=payload).status_code==200
    cfg=db_session.query(AIConfig).one()
    assert 'fixture-only' not in cfg.api_key_encrypted
    assert Fernet(key.encode()).decrypt(cfg.api_key_encrypted.encode()).decode()==payload['api_key']
    result=client.get('/api/v1/admin/ai-config',headers=auth_headers)
    assert result.json()[0]['has_key'] is True
    assert payload['api_key'] not in result.text and cfg.api_key_encrypted not in result.text
    monkeypatch.setattr(settings,'ai_provider','openai_compatible')
    provider=configured_provider(db_session)
    assert provider.api_key==payload['api_key'] and provider.model=='vision-fixture'


def test_non_admin_cannot_store_provider_keys(client,auth_headers):
    assert client.put('/api/v1/admin/ai-config',headers=auth_headers,json={
        'provider':'openai_compatible','api_key':'fixture-only-key'}).status_code==403


def test_provider_disable_and_daily_limit_are_enforced(db_session,monkeypatch):
    import pytest
    from app.models.db_models import AIUsageLog
    from app.ai.provider import AIUnavailableError
    monkeypatch.setattr(settings,'ai_provider','openai_compatible')
    cfg=AIConfig(provider='openai_compatible',enabled=False,usage_limit_per_day=1)
    db_session.add(cfg);db_session.commit()
    with pytest.raises(AIUnavailableError,match='disabled'):configured_provider(db_session)
    cfg.enabled=True
    db_session.add(AIUsageLog(provider='openai_compatible',success=True));db_session.commit()
    with pytest.raises(AIUnavailableError,match='limit'):configured_provider(db_session)
