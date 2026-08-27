"""Importer adapters that turn upstream payloads into listen events.

Every adapter produces the normalized event dict consumed by
``StatsService.record_imported_events``; see :mod:`src.importers.events`
for the shared shape and deterministic key rules.
"""
