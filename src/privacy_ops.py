"""Compatibility facade for retention, archive, and deletion operations."""

from src.privacy_archive import export_user_data, import_user_data
from src.privacy_constants import (
    EXPORT_FORMAT_VERSION,
    IMPORT_MAX_DURATION_SEC,
    IMPORT_MAX_PAYLOAD_BYTES,
    IMPORT_MAX_RECORDS,
    IMPORT_MAX_TEXT_LENGTH,
    RETENTION_MAX_DAYS,
    RETENTION_MIN_DAYS,
    RETENTION_PERMANENT,
    SUPPORTED_IMPORT_FORMAT_VERSIONS,
)
from src.privacy_deletion import delete_user_data, list_users, preview_delete_user
from src.privacy_retention import (
    apply_retention_purge,
    get_retention_days,
    get_storage_stats,
    preview_retention_purge,
    set_retention_days,
    validate_retention_days,
)

__all__ = [
    "EXPORT_FORMAT_VERSION",
    "IMPORT_MAX_DURATION_SEC",
    "IMPORT_MAX_PAYLOAD_BYTES",
    "IMPORT_MAX_RECORDS",
    "IMPORT_MAX_TEXT_LENGTH",
    "RETENTION_MAX_DAYS",
    "RETENTION_MIN_DAYS",
    "RETENTION_PERMANENT",
    "SUPPORTED_IMPORT_FORMAT_VERSIONS",
    "apply_retention_purge",
    "delete_user_data",
    "export_user_data",
    "get_retention_days",
    "get_storage_stats",
    "import_user_data",
    "list_users",
    "preview_delete_user",
    "preview_retention_purge",
    "set_retention_days",
    "validate_retention_days",
]
