"""Tests for offline Ed25519 Supporter Key verification, encrypted storage, and routes."""

from __future__ import annotations

import base64
import json
import logging
import sqlite3

import pytest
from httpx import ASGITransport, AsyncClient

from src import config, supporter
from src.main import app
from src.schema import get_meta_value, init_db, set_meta_value
from src.secretbox import is_encrypted
from src.sqlite import connect_db
from tests.supporter_vectors import (
    EXTRA_FIELD_KEY,
    PATRON_KEY,
    PERSONAL_KEY,
    ROTATED_KEY,
    TEST_PUB1_PEM,
    TEST_PUB2_PEM,
)


def _b64u_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64u_decode(segment: str) -> bytes:
    pad = (4 - (len(segment) % 4)) % 4
    return base64.urlsafe_b64decode(segment + ("=" * pad))


@pytest.fixture()
def isolated_supporter(monkeypatch, tmp_path):
    db_path = str(tmp_path / "supporter-test.sqlite")
    monkeypatch.setattr(config, "DATABASE_PATH", db_path)
    for var in (
        "STATS_SUPPORTER_KEY",
        "STATS_SUPPORTER_SHOW_HEADER",
        "STATS_API_TOKEN",
        "STATS_READ_ONLY_TOKEN",
    ):
        monkeypatch.delenv(var, raising=False)
    pub1 = supporter.parse_public_key_pem(TEST_PUB1_PEM)
    monkeypatch.setattr(supporter, "TRUSTED_PUBLIC_KEYS_PEM", (TEST_PUB1_PEM,))
    monkeypatch.setattr(supporter, "TRUSTED_PUBLIC_KEYS", (pub1,))
    supporter._WARNED_INVALID_SIGNATURES.clear()
    return db_path, pub1


def test_embedded_production_public_key_loads_and_rejects_test_vectors():
    assert len(supporter.TRUSTED_PUBLIC_KEYS_PEM) >= 1
    assert len(supporter.TRUSTED_PUBLIC_KEYS) == len(supporter.TRUSTED_PUBLIC_KEYS_PEM)
    for key_bytes in supporter.TRUSTED_PUBLIC_KEYS:
        assert len(key_bytes) == 32
        point = supporter._decode_point(key_bytes)
        assert point is not None
        assert not supporter._is_small_order(point)
    # Throwaway test keys must never verify against the embedded production key
    assert supporter.verify_supporter_key(PERSONAL_KEY) is None
    assert supporter.verify_supporter_key(PATRON_KEY) is None
    assert supporter.verify_supporter_key(ROTATED_KEY) is None
    assert supporter.validate_supporter_key(PERSONAL_KEY) == (None, "supporter_key_invalid")
    # Empty key ring also fails closed
    assert supporter.verify_supporter_key(PERSONAL_KEY, public_keys=()) is None
    assert supporter.validate_supporter_key(PERSONAL_KEY, public_keys=()) == (
        None,
        "supporter_key_invalid",
    )


def test_parse_public_key_pem_validation_and_small_order():
    escaped = TEST_PUB1_PEM.replace("\n", "\\n")
    raw1 = supporter.parse_public_key_pem(escaped)
    assert len(raw1) == 32

    for bad in (
        "",
        "   ",
        "not-a-pem",
        "-----BEGIN PUBLIC KEY-----\n-----END PUBLIC KEY-----",
        "-----BEGIN PUBLIC KEY-----\n!!!bad!!!\n-----END PUBLIC KEY-----",
        "-----BEGIN PUBLIC KEY-----\n"
        + base64.b64encode(b"\x00" * 10).decode("ascii")
        + "\n-----END PUBLIC KEY-----",
    ):
        with pytest.raises(ValueError):
            supporter.parse_public_key_pem(bad)

    identity_der = supporter._SPKI_ED25519_PREFIX + b"\x01" + (b"\x00" * 31)
    identity_pem = (
        "-----BEGIN PUBLIC KEY-----\n"
        + base64.b64encode(identity_der).decode("ascii")
        + "\n-----END PUBLIC KEY-----"
    )
    with pytest.raises(ValueError):
        supporter.parse_public_key_pem(identity_pem)


def test_verify_ed25519_key_rotation_and_security_rejections():
    pub1 = supporter.parse_public_key_pem(TEST_PUB1_PEM)
    pub2 = supporter.parse_public_key_pem(TEST_PUB2_PEM)

    for token, expected_tier in (
        (PERSONAL_KEY, "personal"),
        (PATRON_KEY, "patron"),
        (EXTRA_FIELD_KEY, "personal"),
    ):
        payload = supporter.verify_supporter_key(f"  {token} \n", public_keys=(pub1,))
        assert payload is not None
        assert payload.tier == expected_tier

    assert supporter.verify_supporter_key(ROTATED_KEY, public_keys=(pub1,)) is None
    rotated = supporter.verify_supporter_key(ROTATED_KEY, public_keys=(pub1, pub2))
    assert rotated is not None
    assert rotated.tier == "patron"
    assert rotated.order_id == "ORD-0004"

    _, payload_b64u, sig_b64u = PERSONAL_KEY.split(".")
    msg = f"NS1.{payload_b64u}".encode("ascii")
    sig = bytearray(_b64u_decode(sig_b64u))
    assert supporter.verify_ed25519(pub1, msg, bytes(sig)) is True

    # Reject tampered payload / signature
    tampered_sig = bytearray(sig)
    tampered_sig[0] ^= 0x01
    assert supporter.verify_ed25519(pub1, msg, bytes(tampered_sig)) is False
    assert supporter.verify_ed25519(pub1, msg + b"x", bytes(sig)) is False

    # Reject non-canonical S >= L (Ed25519 malleability)
    non_canonical = bytearray(sig)
    non_canonical[32:] = supporter._L.to_bytes(32, "little")
    assert supporter.verify_ed25519(pub1, msg, bytes(non_canonical)) is False

    # Reject invalid point / wrong sizes / small-order key
    assert supporter.verify_ed25519(pub1[:31], msg, bytes(sig)) is False
    assert supporter.verify_ed25519(pub1, msg, bytes(sig[:63])) is False
    assert supporter.verify_ed25519(b"\x01" + (b"\x00" * 31), msg, bytes(sig)) is False
    bad_r = bytearray(sig)
    bad_r[:32] = supporter._P.to_bytes(32, "little")
    assert supporter.verify_ed25519(pub1, msg, bytes(bad_r)) is False


def test_validate_supporter_key_schema_validation():
    dummy_sig = _b64u_encode(b"\x11" * 64)

    for bad_token in (
        None,
        123,
        "",
        "   ",
        "PL1.abc." + dummy_sig,
        "NS1.onlytwo",
        "NS1.bad+char." + dummy_sig,
        "NS1." + ("a" * 2100) + "." + dummy_sig,
        f"NS1.{_b64u_encode(b'{not-json')}.{dummy_sig}",
    ):
        assert supporter.validate_supporter_key(bad_token) == (None, "supporter_key_format")

    for bad_payload in (
        [],
        {"v": 2, "tier": "personal", "oid": "ORD-1", "iat": "2026-04-17"},
        {"v": True, "tier": "personal", "oid": "ORD-1", "iat": "2026-04-17"},
        {"v": 1, "tier": "vip", "oid": "ORD-1", "iat": "2026-04-17"},
        {"v": 1, "tier": "personal", "oid": "", "iat": "2026-04-17"},
        {"v": 1, "tier": "personal", "oid": "  ORD-1  ", "iat": "2026-04-17"},
        {"v": 1, "tier": "personal", "oid": "bad\noid", "iat": "2026-04-17"},
        {"v": 1, "tier": "personal", "oid": "x" * 129, "iat": "2026-04-17"},
        {"v": 1, "tier": "personal", "oid": "ORD-1", "iat": "2026-4-17"},
        {"v": 1, "tier": "personal", "oid": "ORD-1", "iat": "2026-02-30"},
    ):
        seg = _b64u_encode(json.dumps(bad_payload).encode("utf-8"))
        assert supporter.validate_supporter_key(f"NS1.{seg}.{dummy_sig}") == (
            None,
            "supporter_key_format",
        )


def test_masking_helpers_never_expose_full_secret():
    masked_key = supporter.mask_key(PERSONAL_KEY)
    assert masked_key.endswith("…")
    assert len(masked_key) <= 19
    assert PERSONAL_KEY.split(".")[2] not in masked_key

    assert supporter.mask_order_id("AB") == "•••••AB"
    assert supporter.mask_order_id("ORD-0001") == "•••••001"
    assert supporter.mask_order_id("ORD-123456789") == "ORD-•••••789"


@pytest.mark.asyncio
async def test_read_paths_do_not_create_missing_database(isolated_supporter, tmp_path):
    missing_db = tmp_path / "does-not-exist.sqlite"
    summary = await supporter.about_supporter_summary(db_path=str(missing_db))
    assert summary == {
        "active": False,
        "tier": None,
        "issued_at": None,
        "show_in_header": True,
    }
    assert await supporter.log_startup_notice(db_path=str(missing_db)) is True
    assert not missing_db.exists()

    # Empty SQLite file without schema_meta stays untouched
    empty_db = tmp_path / "empty.sqlite"
    sqlite3.connect(str(empty_db)).close()
    state = await supporter.resolve_supporter_state(db_path=str(empty_db))
    assert state["status"] == "inactive"
    with sqlite3.connect(str(empty_db)) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_meta'"
        ).fetchall()
    assert tables == []


@pytest.mark.asyncio
async def test_encrypted_db_precedence_and_show_header_flags(isolated_supporter, monkeypatch):
    db_path, _ = isolated_supporter
    await init_db()

    monkeypatch.setenv("STATS_SUPPORTER_KEY", PATRON_KEY)
    monkeypatch.setenv("STATS_SUPPORTER_SHOW_HEADER", "false")
    env_state = await supporter.resolve_supporter_state()
    assert env_state["active"] is True
    assert env_state["tier"] == "patron"
    assert env_state["origin"] == "env"
    assert env_state["env_configured"] is True
    assert env_state["can_clear"] is False
    assert env_state["show_in_header"] is False

    # DB overrides env and stores secretbox ciphertext
    await supporter.save_supporter_key(f"  {PERSONAL_KEY}  ")
    async with connect_db(db_path) as db:
        raw_meta = await get_meta_value(db, supporter.SUPPORTER_KEY_META_KEY)
    assert raw_meta is not None
    assert is_encrypted(raw_meta)
    assert PERSONAL_KEY not in raw_meta

    db_state = await supporter.resolve_supporter_state()
    assert db_state["active"] is True
    assert db_state["tier"] == "personal"
    assert db_state["origin"] == "db"
    assert db_state["env_configured"] is True
    assert db_state["can_clear"] is True
    assert db_state["order_preview"] == "•••••001"

    await supporter.save_supporter_show_header(True)
    toggled = await supporter.resolve_supporter_state()
    assert toggled["show_in_header"] is True

    await supporter.clear_supporter_key()
    reverted = await supporter.resolve_supporter_state()
    assert reverted["tier"] == "patron"
    assert reverted["origin"] == "env"
    assert reverted["can_clear"] is False


@pytest.mark.asyncio
async def test_invalid_db_and_env_warnings_and_startup_notice(
    isolated_supporter, monkeypatch, caplog
):
    db_path, _ = isolated_supporter
    await init_db()

    # Inactive DB emits startup notice once
    with caplog.at_level(logging.INFO, logger="navidrome-stat"):
        assert await supporter.log_startup_notice() is True
    assert supporter.SUPPORT_URL in caplog.text

    # Corrupt DB key overrides valid env and masks secret from logs
    monkeypatch.setenv("STATS_SUPPORTER_KEY", PATRON_KEY)
    async with connect_db(db_path) as db:
        await set_meta_value(db, supporter.SUPPORTER_KEY_META_KEY, "secretbox:v1:corrupted")
        await db.commit()

    with caplog.at_level(logging.WARNING, logger="navidrome-stat"):
        state = await supporter.resolve_supporter_state()
        notice = await supporter.log_startup_notice()
    assert state["status"] == "invalid"
    assert state["origin"] == "db"
    assert state["active"] is False
    assert state["can_clear"] is True
    assert notice is False

    # Unencrypted value treated as corrupt
    async with connect_db(db_path) as db:
        await set_meta_value(db, supporter.SUPPORTER_KEY_META_KEY, "plaintext-not-sealed")
        await db.commit()
    state_plain = await supporter.resolve_supporter_state()
    assert state_plain["status"] == "invalid"
    assert state_plain["origin"] == "db"

    await supporter.clear_supporter_key()

    # Invalid env key warns only once and never leaks key in logs
    caplog.clear()
    monkeypatch.setenv("STATS_SUPPORTER_KEY", ROTATED_KEY)
    with caplog.at_level(logging.WARNING, logger="navidrome-stat"):
        s1 = await supporter.resolve_supporter_state()
        s2 = await supporter.resolve_supporter_state()
    assert s1["status"] == "invalid"
    assert s2["origin"] == "env"
    assert ROTATED_KEY not in caplog.text
    assert sum(1 for r in caplog.records if "Ignoring invalid STATS_SUPPORTER_KEY" in r.message) == 1


@pytest.mark.asyncio
async def test_supporter_routes_auth_and_zero_leakage(isolated_supporter, monkeypatch, caplog):
    await init_db()

    # Public /api/about works without auth
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        about_resp = await ac.get("/api/about")
    assert about_resp.status_code == 200
    assert about_resp.json()["supporter"] == {
        "active": False,
        "tier": None,
        "issued_at": None,
        "show_in_header": True,
    }

    monkeypatch.setenv("STATS_API_TOKEN", "admin-secret")
    monkeypatch.setenv("STATS_READ_ONLY_TOKEN", "viewer-secret")
    admin_hdrs = {"Authorization": "Bearer admin-secret"}
    viewer_hdrs = {"Authorization": "Bearer viewer-secret"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Unauthenticated blocked
        for method, path in (
            ("GET", "/api/supporter"),
            ("PUT", "/api/supporter-key"),
            ("DELETE", "/api/supporter-key"),
            ("PATCH", "/api/supporter/preferences"),
        ):
            r = await ac.request(method, path)
            assert r.status_code == 401

        # Read-only viewer blocked on all supporter endpoints
        for method, path, body in (
            ("GET", "/api/supporter", None),
            ("PUT", "/api/supporter-key", {"key": PERSONAL_KEY}),
            ("DELETE", "/api/supporter-key", None),
            ("PATCH", "/api/supporter/preferences", {"show_in_header": False}),
        ):
            r = await ac.request(method, path, headers=viewer_hdrs, json=body)
            assert r.status_code == 403

        # Admin validation checks
        bad_fmt = await ac.put("/api/supporter-key", headers=admin_hdrs, json={"key": "bad"})
        assert bad_fmt.status_code == 400
        assert bad_fmt.json()["detail"] == "supporter_key_format"

        bad_body = await ac.put("/api/supporter-key", headers=admin_hdrs)
        assert bad_body.status_code == 400

        bad_sig = await ac.put("/api/supporter-key", headers=admin_hdrs, json={"key": ROTATED_KEY})
        assert bad_sig.status_code == 400
        assert bad_sig.json()["detail"] == "supporter_key_invalid"

        # Activate valid key
        with caplog.at_level(logging.DEBUG):
            put_ok = await ac.put(
                "/api/supporter-key", headers=admin_hdrs, json={"key": f" {PERSONAL_KEY} "}
            )
        assert put_ok.status_code == 200
        sup_doc = put_ok.json()["supporter"]
        assert sup_doc["active"] is True
        assert sup_doc["tier"] == "personal"
        assert sup_doc["issued_at"] == "2026-04-17"
        assert sup_doc["order_preview"] == "•••••001"
        assert PERSONAL_KEY not in put_ok.text
        assert "ORD-0001" not in put_ok.text

        # Preferences toggle reflects on GET /api/supporter & viewer GET /api/about
        patch_ok = await ac.patch(
            "/api/supporter/preferences", headers=admin_hdrs, json={"show_in_header": False}
        )
        assert patch_ok.status_code == 200
        assert patch_ok.json()["supporter"]["show_in_header"] is False

        viewer_about = await ac.get("/api/about", headers=viewer_hdrs)
        assert viewer_about.status_code == 200
        about_sup = viewer_about.json()["supporter"]
        assert about_sup == {
            "active": True,
            "tier": "personal",
            "issued_at": "2026-04-17",
            "show_in_header": False,
        }

        get_ok = await ac.get("/api/supporter", headers=admin_hdrs)
        assert get_ok.status_code == 200
        assert PERSONAL_KEY not in get_ok.text

        del_ok = await ac.delete("/api/supporter-key", headers=admin_hdrs)
        assert del_ok.status_code == 200
        assert del_ok.json()["supporter"]["active"] is False

    assert PERSONAL_KEY not in caplog.text
    assert ROTATED_KEY not in caplog.text


@pytest.mark.asyncio
async def test_secret_key_missing_or_unreadable_never_creates_key_or_blocks_startup(
    isolated_supporter,
):
    from src.secretbox import key_path

    db_path, _ = isolated_supporter
    await init_db()
    await supporter.save_supporter_key(PERSONAL_KEY)
    secret_path = key_path(db_path)
    assert secret_path.exists()
    original_secret_bytes = secret_path.read_bytes()

    # Scenario 1: DB-only restore (secret.key missing) must NOT create a new secret.key on reads
    secret_path.unlink()
    missing_state = await supporter.resolve_supporter_state()
    assert missing_state["active"] is False
    assert missing_state["status"] == "invalid"
    assert missing_state["origin"] == "db"
    assert missing_state["can_clear"] is True
    assert not secret_path.exists()

    # Restoring the original secret.key immediately recovers the active key
    secret_path.write_bytes(original_secret_bytes)
    recovered = await supporter.resolve_supporter_state()
    assert recovered["active"] is True
    assert recovered["tier"] == "personal"

    # Scenario 2: Unreadable secret.key (PermissionError) must never crash startup or /api/about
    secret_path.chmod(0o000)
    try:
        assert await supporter.log_startup_notice() is False
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            about_resp = await ac.get("/api/about")
            sup_resp = await ac.get("/api/supporter")
        assert about_resp.status_code == 200
        assert about_resp.json()["supporter"]["active"] is False
        assert sup_resp.status_code == 200
        assert sup_resp.json()["supporter"]["status"] == "invalid"
    finally:
        secret_path.chmod(0o600)


def test_docker_compose_forwards_supporter_env_vars():
    from pathlib import Path

    compose_text = (Path(__file__).resolve().parent.parent / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
    assert "STATS_SUPPORTER_KEY: ${STATS_SUPPORTER_KEY:-}" in compose_text
    assert (
        "STATS_SUPPORTER_SHOW_HEADER: ${STATS_SUPPORTER_SHOW_HEADER:-true}" in compose_text
    )
