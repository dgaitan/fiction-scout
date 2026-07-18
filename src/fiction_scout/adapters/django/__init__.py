"""Deliberately empty.

This package is also the Django app named in `INSTALLED_APPS`
(`fiction_scout.adapters.django`), so Django imports this module while
populating the app registry, before any app's models are safe to define.
Re-exporting `SearchableMixin` here (a `models.Model` subclass, defined in
`mixin.py`) would import it at that point and raise `AppRegistryNotReady`.
Import it from `fiction_scout.adapters.django.mixin` directly.
"""

from __future__ import annotations
