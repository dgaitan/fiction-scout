from __future__ import annotations

from typing import Any

from django.db import models

from fiction_scout.adapters.django.mixin import SearchableMixin
from fiction_scout.strategies import search_using_full_text, search_using_prefix


class Article(SearchableMixin, models.Model):
    title = models.CharField(max_length=200)
    body = models.TextField()
    deleted_at = models.DateTimeField(null=True, blank=True)

    soft_delete_field = "deleted_at"

    class Meta:
        app_label = "django_app"

    def __str__(self) -> str:
        return self.title

    @search_using_prefix("title")
    @search_using_full_text("body")
    def to_searchable_array(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "body": self.body}
