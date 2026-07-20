# `collection` engine

In-memory search: filters every record of a model in Python on each search
call. No indexing step, no external service, no database-specific features
required — `update`/`delete`/`flush` are no-ops for the same reason as the
`database` engine (results always reflect current data).

Select it with:

```python
FICTION_SCOUT = {"driver": "collection"}
```

## When to use it

Prototypes, tests, and datasets small enough that scanning every row per
search is fine — a few hundred records, not thousands. It reads every
record via `adapter.chunk_records(model, chunk_size=500)` and filters in
Python, so it scales with total row count on every query, not with an
index.

Like `database`, `Builder.where()`/`.where_in()`/`.where_not_in()` and
`.with_trashed()`/`.only_trashed()` are honored — but the field name means
something different here: matching happens against the
**`to_searchable_array()` dict** this engine already read into memory, not
against the model's real ORM fields. `.where_in("director", [...])` matches
whatever `to_searchable_array()`'s `"director"` key holds (a related
model's `.name`, if that's what you returned there) — no relation-traversal
syntax needed or possible, unlike on
[`database`](database.md#where-clause-fields-are-real-query-paths). See
[Searching: where clauses](../searching.md#where-clauses) for the full
per-engine breakdown.
