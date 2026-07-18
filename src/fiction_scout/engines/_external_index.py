"""Shared `map()` logic for engines whose index holds documents, not live rows.

An external search index (Algolia, Meilisearch, Elasticsearch, ...) can only
return matched document ids — `map()` on these engines is always "extract
ids, then fetch models", unlike `DatabaseEngine.map()`, which reads live rows
directly off the query it already built. Sprint 7 (Algolia) introduces this
helper; Sprints 8-9 (Meilisearch, Elasticsearch) reuse it rather than
re-deriving the same logic a third time.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fiction_scout.protocols import SearchableAdapter


def fetch_matched_models(
    adapter: SearchableAdapter, model: type, ids: Sequence[Any]
) -> list[Any]:
    """Fetch `model` instances for `ids`, preserving match order.

    External index document ids are always strings, while an ORM's own
    scout key may not be (an integer primary key, for example) — matching
    is done on `str()` of both sides so this holds regardless of the scout
    key's underlying type. Ids with no corresponding row (e.g. deleted since
    the index was last synced) are silently skipped, matching
    `CollectionEngine.map`'s existing behavior.
    """
    instances = adapter.fetch_by_ids(model, ids)
    by_key = {str(adapter.get_scout_key(instance)): instance for instance in instances}
    return [by_key[str(key)] for key in ids if str(key) in by_key]
