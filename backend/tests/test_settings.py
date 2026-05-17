from app.config.settings import Settings


def test_database_settings_default_to_postgres(monkeypatch):
    """默认配置指向本地 PostgreSQL，团队开发和正式运行使用同一类数据库。"""
    monkeypatch.delenv("TRPG_DATABASE_BACKEND", raising=False)
    monkeypatch.delenv("DATABASE_BACKEND", raising=False)
    monkeypatch.delenv("TRPG_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    settings = Settings()

    assert settings.database_backend == "postgres"
    assert settings.database_url == "postgresql://trpg:trpg@localhost:5432/trpg_agent"
    assert settings.memory_db_path == "data/context_memory.sqlite3"


def test_database_settings_can_read_postgres_env(monkeypatch):
    """正式运行可通过环境变量覆盖目标 PostgreSQL。"""
    monkeypatch.setenv("TRPG_DATABASE_BACKEND", "postgres")
    monkeypatch.setenv("TRPG_DATABASE_URL", "postgresql://trpg:trpg@localhost:5432/trpg_agent")

    settings = Settings()

    assert settings.database_backend == "postgres"
    assert settings.database_url == "postgresql://trpg:trpg@localhost:5432/trpg_agent"


def test_sqlite_fallback_can_override_memory_path(monkeypatch):
    """SQLite fallback 保留独立路径；默认 PostgreSQL URL 在该模式下不会被使用。"""
    monkeypatch.setenv("TRPG_DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("TRPG_MEMORY_DB_PATH", "data/local-demo.sqlite3")
    monkeypatch.delenv("TRPG_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    settings = Settings()

    assert settings.database_backend == "sqlite"
    assert settings.database_url == "postgresql://trpg:trpg@localhost:5432/trpg_agent"
    assert settings.memory_db_path == "data/local-demo.sqlite3"
