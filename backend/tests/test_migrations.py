from pathlib import Path
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata
from sqlalchemy import create_engine, inspect
from app.core.config import settings
from app.core.database import Base


def test_fresh_database_upgrade_matches_models_and_downgrade(tmp_path, monkeypatch):
    url = f'sqlite:///{tmp_path / "migrated.sqlite"}'
    monkeypatch.setattr(settings, 'database_url', url)
    config = Config(str(Path(__file__).parents[1] / 'alembic.ini'))
    config.set_main_option('script_location',str(Path(__file__).parents[1] / 'migrations'))
    command.upgrade(config,'head')
    engine=create_engine(url)
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection),Base.metadata) == []
        assert len(inspect(connection).get_table_names()) == len(Base.metadata.tables)+1
    command.downgrade(config,'base')
    with engine.connect() as connection:
        assert inspect(connection).get_table_names() == ['alembic_version']
    engine.dispose()
