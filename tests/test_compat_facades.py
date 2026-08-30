"""Compatibility facades stay thin while behavior lives in focused modules."""

import src.database as database
import src.privacy_ops as privacy_ops
import src.stats_queries as stats_queries
from src.privacy_archive import export_user_data, import_user_data
from src.privacy_deletion import delete_user_data
from src.privacy_retention import apply_retention_purge
from src.stats_query_history import get_playback_history
from src.stats_query_overview import get_summary
from src.stats_query_rankings import get_top_artists
from src.stats_query_timeline import get_time_bucket_stats


def test_statistics_facades_reexport_category_owned_behaviors():
    assert stats_queries.get_summary is get_summary
    assert stats_queries.get_time_bucket_stats is get_time_bucket_stats
    assert stats_queries.get_top_artists is get_top_artists
    assert stats_queries.get_playback_history is get_playback_history
    assert database.get_summary is get_summary
    assert database.get_playback_history is get_playback_history


def test_privacy_facade_reexports_behavior_owned_operations():
    assert privacy_ops.apply_retention_purge is apply_retention_purge
    assert privacy_ops.export_user_data is export_user_data
    assert privacy_ops.import_user_data is import_user_data
    assert privacy_ops.delete_user_data is delete_user_data
