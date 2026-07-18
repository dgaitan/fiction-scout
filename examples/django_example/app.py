#!/usr/bin/env python
"""End-to-end smoke check for the Django example: migrate, save, search.

Run directly (`python examples/django_example/app.py`) or via
`nox -s smoke`. Exits non-zero if the searched-for post isn't found, so this
doubles as a real check rather than only a demo script.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "example_project.settings")

import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402
from example_project.blog.models import Post  # noqa: E402


def main() -> None:
    call_command("migrate", run_syncdb=True, verbosity=0)

    Post.objects.create(title="Star Trek II", body="The Wrath of Khan")
    Post.objects.create(title="Star Wars", body="A New Hope")

    results = Post.search("Wrath of Khan").get()
    titles = [post.title for post in results]
    print(f"Search for 'Wrath of Khan' matched: {titles}")

    assert titles == ["Star Trek II"], f"expected exactly one match, got {titles}"
    print("OK")


if __name__ == "__main__":
    main()
