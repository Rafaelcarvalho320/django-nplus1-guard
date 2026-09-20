"""django-nplus1-guard: catch N+1 queries before they reach production.

Three entry points for the same detector:

* ``record()`` / ``build_report()`` to inspect any block of code;
* ``NPlusOneMiddleware`` to watch requests during development;
* a pytest plugin to turn an N+1 into a failing test in CI.
"""

from nplus1_guard.conf import Config, get_config
from nplus1_guard.fingerprint import fingerprint, summarize, table_of
from nplus1_guard.origin import Origin, find_origin
from nplus1_guard.recorder import Query, Recorder, record
from nplus1_guard.report import (
    DEFAULT_THRESHOLD,
    Duplicate,
    Report,
    build_report,
)

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_THRESHOLD",
    "Config",
    "Duplicate",
    "Origin",
    "Query",
    "Recorder",
    "Report",
    "__version__",
    "build_report",
    "find_origin",
    "fingerprint",
    "get_config",
    "record",
    "summarize",
    "table_of",
]
