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
`.with_trashed()`/`.only_trashed()` are honored — filtering happens against
the same searchable-array dicts this engine reads into memory.
