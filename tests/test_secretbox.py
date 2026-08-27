"""At-rest credential encryption: key handling, box roundtrip, storage wiring."""

import asyncio
import sqlite3

import pytest

from src.database import init_db, save_server
from src.secretbox import (
    KEY_FILENAME,
    SecretBoxError,
    decrypt,
    encrypt,
    key_path,
    load_or_create_key,
)


@pytest.fixture
def isolated_env(monkeypatch, tmp_path):
    db_file = tmp_path / "stats.db"
    monkeypatch.setattr("src.config.DATABASE_PATH", str(db_file))
    return tmp_path


def test_load_or_create_key_creates_owner_only_32_byte_key(isolated_env):
    key = load_or_create_key()
    path = key_path()

    assert len(key) == 32
    assert path.name == KEY_FILENAME
    assert (path.stat().st_mode & 0o777) == 0o600
    assert load_or_create_key() == key


def test_roundtrip_with_unique_ciphertexts(isolated_env):
    first = encrypt("plain-password")
    second = encrypt("plain-password")

    assert first != second
    assert first.startswith("enc:v1:")
    assert decrypt(first) == "plain-password"
    assert decrypt(second) == "plain-password"


def test_decrypt_rejects_tampered_ciphertext(isolated_env):
    token = encrypt("plain-password")
    head, payload = token.rsplit(":", 1)
    flipped = "A" if payload[-2] != "A" else "B"
    tampered = f"{head}:{payload[:-2]}{flipped}{payload[-1]}"

    with pytest.raises(SecretBoxError):
        decrypt(tampered)


def test_decrypt_rejects_unprefixed_input(isolated_env):
    with pytest.raises(SecretBoxError):
        decrypt("plaintext")


def test_decrypt_fails_when_key_file_missing(isolated_env):
    token = encrypt("plain-password")
    key_path().unlink()

    with pytest.raises(SecretBoxError):
        decrypt(token)


def test_corrupt_key_file_reports_error(isolated_env):
    key_path().write_bytes(b"not-base64!!")

    with pytest.raises(SecretBoxError):
        load_or_create_key()


def test_saved_server_password_never_plaintext_on_disk(isolated_env):
    asyncio.run(_assert_ciphertext_at_rest(str(isolated_env / "stats.db")))


async def _assert_ciphertext_at_rest(db_path: str):
    await init_db(db_path)
    await save_server(
        {
            "id": "srv1",
            "display_name": "Main",
            "url": "http://navidrome.example.invalid",
            "username": "user",
            "password": "super-secret",
            "enabled": True,
        },
        db_path=db_path,
    )

    conn = sqlite3.connect(db_path)
    stored = conn.execute(
        "SELECT password FROM servers WHERE id = 'srv1'"
    ).fetchone()[0]
    conn.close()

    assert stored.startswith("enc:v1:")
    assert "super-secret" not in stored


def test_migration_rewraps_legacy_plaintext_credentials(isolated_env):
    asyncio.run(_assert_legacy_rewrite(str(isolated_env / "stats.db")))


async def _assert_legacy_rewrite(db_path: str):
    await init_db(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE schema_meta SET value='9' WHERE key='schema_version'")
    conn.execute(
        "INSERT INTO servers (id, display_name, url, username, password, enabled,"
        " created_at, updated_at)"
        " VALUES ('legacy', 'Legacy', 'http://navidrome.example.invalid', 'u',"
        " 'old-secret', 1, '2024-01-01', '2024-01-01')"
    )
    conn.execute(
        "INSERT INTO schema_meta (key, value)"
        " VALUES ('source_password', 'fallback-old-secret')"
    )
    conn.commit()
    conn.close()

    await init_db(db_path)

    conn = sqlite3.connect(db_path)
    rows = {
        "server": conn.execute(
            "SELECT password FROM servers WHERE id='legacy'"
        ).fetchone()[0],
        "fallback": conn.execute(
            "SELECT value FROM schema_meta WHERE key='source_password'"
        ).fetchone()[0],
    }
    conn.close()

    for stored in rows.values():
        assert stored.startswith("enc:v1:")
        assert "old-secret" not in stored


def test_missing_key_degrades_to_empty_password_without_raising(isolated_env):
    asyncio.run(_assert_missing_key_degrades(str(isolated_env / "stats.db")))


def test_fallback_saved_password_encrypted_at_rest(isolated_env):
    asyncio.run(_assert_fallback_encrypted(str(isolated_env / "stats.db")))


async def _assert_fallback_encrypted(db_path: str):
    from src.source_config import (
        get_saved_source_config,
        set_saved_source_config,
    )

    await init_db(db_path)
    await set_saved_source_config(
        url="http://navidrome.example.invalid",
        user="user",
        password="fallback-secret",
        db_path=db_path,
    )

    conn = sqlite3.connect(db_path)
    stored = conn.execute(
        "SELECT value FROM schema_meta WHERE key='source_password'"
    ).fetchone()[0]
    conn.close()

    assert stored.startswith("enc:v1:")
    assert "fallback-secret" not in stored

    saved = await get_saved_source_config(db_path=db_path)
    assert saved["password"] == "fallback-secret"


async def _assert_missing_key_degrades(db_path: str):
    from src.server_registry import get_server, list_servers

    await init_db(db_path)
    await save_server(
        {
            "id": "srv2",
            "display_name": "Aux",
            "url": "http://navidrome.example.invalid",
            "username": "user",
            "password": "another-secret",
            "enabled": True,
        },
        db_path=db_path,
    )
    key_path().unlink()

    servers = await list_servers(db_path=db_path)
    target = await get_server("srv2", db_path=db_path)

    assert servers[0]["password"] == ""
    assert target["password"] == ""
