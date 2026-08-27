"""At-rest protection for saved upstream credentials.

A 32-byte symmetric key lives in ``secret.key`` beside the SQLite file with
owner-only permissions. Saved passwords are stored as ``enc:v1:<base64
nonce|ciphertext>`` using AES-256-GCM. Database copies or backups that travel
without the key file stay sealed; anyone who can read both files can decrypt,
so this is not a defense against a compromised data directory.
"""

from __future__ import annotations

import base64
import binascii
import os
import secrets
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from src import config

KEY_BYTES = 32
NONCE_BYTES = 12
PREFIX = "enc:v1:"
KEY_FILENAME = "secret.key"


class SecretBoxError(RuntimeError):
    """Key material is missing, unreadable, or a payload failed to open."""


def key_path(db_path: str | None = None) -> Path:
    """Resolve the key file location beside the given SQLite database."""
    base = db_path or config.DATABASE_PATH
    return Path(base).absolute().parent / KEY_FILENAME


def load_or_create_key(db_path: str | None = None) -> bytes:
    """Return the existing 32-byte key, creating an owner-only file if absent."""
    path = key_path(db_path)
    if path.exists():
        try:
            raw = base64.b64decode(path.read_bytes().strip(), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise SecretBoxError("Credential key file is corrupt") from exc
        if len(raw) != KEY_BYTES:
            raise SecretBoxError("Credential key file has the wrong length")
        return raw

    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(KEY_BYTES)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(base64.b64encode(key))
    os.chmod(path, 0o600)
    return key


def read_key_if_present(db_path: str | None = None) -> bytes | None:
    """Return the stored key without creating it, or None."""
    path = key_path(db_path)
    if not path.exists():
        return None
    try:
        raw = base64.b64decode(path.read_bytes().strip(), validate=True)
    except OSError:
        return None
    except (binascii.Error, ValueError) as exc:
        raise SecretBoxError("Credential key file is corrupt") from exc
    return raw if len(raw) == KEY_BYTES else None


def is_encrypted(value: object) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


def encrypt(value: str, key: bytes | None = None, *, db_path: str | None = None) -> str:
    if value == "":
        return value
    key_bytes = key if key is not None else load_or_create_key(db_path)
    nonce = secrets.token_bytes(NONCE_BYTES)
    ciphertext = AESGCM(key_bytes).encrypt(nonce, value.encode("utf-8"), None)
    return PREFIX + base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt(value: str, key: bytes | None = None, *, db_path: str | None = None) -> str:
    if not isinstance(value, str) or not value.startswith(PREFIX):
        raise SecretBoxError("Value is not a v1 encrypted credential")
    try:
        raw = base64.b64decode(value[len(PREFIX):], validate=True)
        if len(raw) <= NONCE_BYTES:
            raise ValueError("payload too short")
        nonce, ciphertext = raw[:NONCE_BYTES], raw[NONCE_BYTES:]
        key_bytes = key if key is not None else load_or_create_key(db_path)
        plain = AESGCM(key_bytes).decrypt(nonce, ciphertext, None)
    except (binascii.Error, InvalidTag, ValueError) as exc:
        raise SecretBoxError("Credential decryption failed") from exc
    return plain.decode("utf-8")


def unwrap(value: str | None, key: bytes | None = None, *, db_path: str | None = None) -> str:
    """Decrypt or degrade to empty string; never raises for storage reads."""
    if not value:
        return ""
    if not is_encrypted(value):
        return ""
    try:
        return decrypt(value, key, db_path=db_path)
    except SecretBoxError:
        return ""
