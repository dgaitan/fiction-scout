# Indexing

How records get into (and out of) a search index — auto-sync, batch import,
and the hooks that let a model control its own indexing.

## Auto-sync on save/delete

Once a model uses `SearchableMixin` and its adapter's sync trigger is wired
up (Django's `post_save`/`post_delete` signals, connected automatically by
`fiction_scout.adapters.django`'s `AppConfig.ready()`), every `save()` and
`delete()` call keeps the index current with no extra code:

```python
post = Post.objects.create(title="Star Trek II", body="The Wrath of Khan")
post.title = "Star Trek II: The Wrath of Khan"
post.save()       # re-indexed automatically
post.delete()     # removed from the index automatically
```

You can also drive this manually, per instance, without touching the row:

```python
post.searchable()     # push this instance to the index right now
post.unsearchable()   # remove this instance from the index right now
```

## Batch import

Auto-sync only covers rows created/changed *after* a model starts using
`SearchableMixin`. To push everything that already exists:

```bash
fiction-scout import myapp.models.Post              # synchronous
fiction-scout queue-import myapp.models.Post         # via the configured dispatcher
```

Or, under Django, the identical functions via the management command bridge:

```bash
python manage.py fiction_scout import myapp.models.Post
python manage.py fiction_scout queue-import myapp.models.Post
```

`import` always runs synchronously, chunking through
`adapter.chunk_records()` (`FictionScoutConfig.chunk_size`, default 500) and
calling `engine.update()` per batch. `queue-import` does the same but routes
each batch through the model's `get_scout_dispatcher()` instead of running
inline — use it for large tables where a synchronous import would block.

```bash
fiction-scout flush myapp.models.Post   # remove every index entry; rows untouched
```

## Pausing sync during bulk operations

Bulk ORM operations (`bulk_create`, `bulk_update`, migrations that touch many
rows) bypass `save()`/`delete()` entirely, so Django's signals never fire for
them — nothing to pause there. But if you're running your *own* loop that
calls `.save()` repeatedly (e.g. a data-fix script), each call would
otherwise trigger a synchronous index write per row. Wrap it:

```python
from fiction_scout.sync.context import without_syncing_to_search

with without_syncing_to_search():
    for post in posts_needing_a_fix:
        post.title = fix_title(post.title)
        post.save()   # no per-row sync while this block runs

# re-sync everything that changed, in one batch, after the fact
Post.objects.filter(id__in=[p.id for p in posts_needing_a_fix]).searchable()
```

`without_syncing_to_search()` nests correctly and is safe across concurrent
async contexts (it's `ContextVar`-based, not a global mutable flag) — see
`fiction_scout.sync.context.is_syncing_paused()` if you're writing a custom
adapter's sync trigger and need to honor the pause yourself.

## Conditionally searchable instances

Override `should_be_searchable()` to exclude instances from the index based
on your own application logic — a draft post that shouldn't be findable
until published, for example:

```python
class Post(SearchableMixin, models.Model):
    status = models.CharField(max_length=20, default="draft")

    def should_be_searchable(self) -> bool:
        return self.status == "published"
```

On `save()`, the Django signal handler checks this per instance: `True`
indexes it, `False` removes it from the index (even if it was previously
indexed and just transitioned to unpublished) — so flipping `status` back
and forth correctly adds and removes the record without any extra code.
Calling `.searchable()` directly bypasses this check — it's a hook for the
*automatic* sync path, not a hard guarantee that an instance is never
indexed.

## Soft delete

Declare `soft_delete_field` on a model — a `ClassVar[str | None]`, `None` by
default:

```python
class Post(SearchableMixin, models.Model):
    deleted_at = models.DateTimeField(null=True, blank=True)
    soft_delete_field = "deleted_at"
```

When that field is set (non-`None`) on save, the instance is removed from
the index rather than updated — `orchestration.should_be_searchable()`
excludes it, and `DjangoAdapter.apply_trashed_filter` filters it out of
`database`-engine queries by default. `Builder.with_trashed()`/
`.only_trashed()` retrieve soft-deleted rows anyway, but **only against the
`database` and `collection` engines** — Algolia and Meilisearch remove a
soft-deleted record from their index entirely rather than keeping it
tagged and filterable. If you need "search including soft-deleted records"
against an external engine, that record simply isn't there to find — this
is a deliberate v1 scope decision, not a bug.
