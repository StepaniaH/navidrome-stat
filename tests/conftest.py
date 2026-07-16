import pytest

pytest_plugins = ("pytest_asyncio",)


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")
