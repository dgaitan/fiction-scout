# Django example

A minimal, runnable Django project using fiction-scout's `database` driver
(no external search service required).

```bash
pip install -e ".[django]"          # from the repo root
python examples/django_example/manage.py migrate
python examples/django_example/manage.py shell
```

```python
>>> from example_project.blog.models import Post
>>> Post.objects.create(title="Star Trek II", body="The Wrath of Khan")
>>> Post.search("Wrath of Khan").get()
[<Post: Star Trek II>]
```

Or run the end-to-end smoke script directly:

```bash
python examples/django_example/app.py
```

`example_project/blog/models.py` shows a `Post` model using
`SearchableMixin`, with `@search_using_prefix`/`@search_using_full_text`
column strategies. Saving a `Post` auto-syncs it via Django's own
`post_save` signal — nothing in this example calls `.searchable()`
manually.

See [`docs/index.md`](../../docs/index.md) for the full walkthrough.
