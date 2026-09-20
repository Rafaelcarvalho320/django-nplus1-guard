"""Settings, read once per access so tests can override them.

Everything lives under a single ``NPLUS1_GUARD`` dict, which keeps one name in
the project's settings instead of six, and makes
``@override_settings(NPLUS1_GUARD={...})`` replace the whole configuration
rather than half of it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from re import Pattern
from typing import Any

from django.conf import settings

SETTINGS_NAME = "NPLUS1_GUARD"

DEFAULTS: dict[str, Any] = {
    # Off unless DEBUG. A detector that runs in production is a detector that
    # slows production down; opt in deliberately if you want it in staging.
    "ENABLED": None,
    "THRESHOLD": 5,
    # Raising turns a silent performance bug into a visible failure. It is the
    # right default for local development and the wrong one for a shared
    # environment, so it follows DEBUG rather than being on outright.
    "RAISE": False,
    "LOG_LEVEL": "WARNING",
    "IGNORE_PATHS": [],
    "IGNORE_TABLES": [],
    "HEADER": True,
}


@dataclass(frozen=True)
class Config:
    enabled: bool
    threshold: int
    raise_on_detection: bool
    log_level: str
    ignore_paths: tuple[Pattern[str], ...] = field(default_factory=tuple)
    ignore_tables: frozenset[str] = frozenset()
    header: bool = True

    def path_ignored(self, path: str) -> bool:
        return any(pattern.search(path) for pattern in self.ignore_paths)

    def table_ignored(self, table: str) -> bool:
        return table.lower() in self.ignore_tables


def get_config() -> Config:
    """Read the current settings. Cheap enough to call per request."""
    raw = {**DEFAULTS, **getattr(settings, SETTINGS_NAME, {})}
    enabled = raw["ENABLED"]
    if enabled is None:
        enabled = bool(settings.DEBUG)
    return Config(
        enabled=bool(enabled),
        threshold=int(raw["THRESHOLD"]),
        raise_on_detection=bool(raw["RAISE"]),
        log_level=str(raw["LOG_LEVEL"]).upper(),
        ignore_paths=tuple(re.compile(p) for p in raw["IGNORE_PATHS"]),
        ignore_tables=frozenset(t.lower() for t in raw["IGNORE_TABLES"]),
        header=bool(raw["HEADER"]),
    )
