import pytest
from pydantic import ValidationError
from app.core.config import Settings


def test_production_refuses_default_secrets_and_sqlite():
    with pytest.raises(ValidationError):Settings(app_env='production',_env_file=None)
    with pytest.raises(ValidationError):Settings(app_env='production',jwt_secret='x'*48,_env_file=None)
    valid=Settings(app_env='production',jwt_secret='x'*48,database_url='postgresql+psycopg://fixture/db',_env_file=None)
    assert valid.app_env=='production'
