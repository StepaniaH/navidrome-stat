import pytest

pytest_plugins = ("pytest_asyncio",)


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def isolated_db(db_path, monkeypatch):
    monkeypatch.setattr("src.database.DB_PATH", db_path)
    monkeypatch.setattr("src.privacy_ops.DB_PATH", db_path)
    return db_path
