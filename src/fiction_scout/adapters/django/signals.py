from __future__ import annotations

from typing import Any

from django.db.models.signals import post_delete, post_save

from fiction_scout import orchestration
from fiction_scout.adapters.django import runtime
from fiction_scout.adapters.django.mixin import SearchableMixin


def _sync_on_save(sender: type, instance: Any, **kwargs: Any) -> None:
    if not isinstance(instance, SearchableMixin):
        return
    adapter = runtime.get_adapter()
    engine_manager = runtime.get_engine_manager()
    dispatcher = runtime.get_dispatcher()
    if instance.should_be_searchable():
        orchestration.make_searchable(
            [instance],
            adapter=adapter,
            engine_manager=engine_manager,
            dispatcher=dispatcher,
        )
    else:
        orchestration.make_unsearchable(
            [instance],
            adapter=adapter,
            engine_manager=engine_manager,
            dispatcher=dispatcher,
        )


def _sync_on_delete(sender: type, instance: Any, **kwargs: Any) -> None:
    if not isinstance(instance, SearchableMixin):
        return
    orchestration.make_unsearchable(
        [instance],
        adapter=runtime.get_adapter(),
        engine_manager=runtime.get_engine_manager(),
        dispatcher=runtime.get_dispatcher(),
    )


def connect_signals() -> None:
    post_save.connect(_sync_on_save, dispatch_uid="fiction_scout_post_save")
    post_delete.connect(_sync_on_delete, dispatch_uid="fiction_scout_post_delete")
