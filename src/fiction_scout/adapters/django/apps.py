from __future__ import annotations

from django.apps import AppConfig


class FictionScoutAppConfig(AppConfig):
    name = "fiction_scout.adapters.django"
    label = "fiction_scout"

    def ready(self) -> None:
        from fiction_scout.adapters.django.signals import connect_signals

        connect_signals()
