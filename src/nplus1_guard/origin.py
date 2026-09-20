"""Finding the line of your code that caused a query.

A report that says "this query ran 200 times" is interesting. A report that
says "this query ran 200 times, from views.py line 42" is actionable, and the
difference between the two is this module.

The stack at the moment a query executes is mostly Django internals. What
matters is the deepest frame that belongs to the project, so the walk starts at
the query and stops at the first frame that is not library code.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from types import FrameType

#: Path fragments that mean "not the user's code". Compared against a path
#: with separators already normalized to forward slashes, so one spelling of
#: each is enough on every platform.
LIBRARY_MARKERS = (
    "/site-packages/",
    "/dist-packages/",
    "/lib/python",
    "/lib64/python",
)

#: Packages that are never the answer, even when installed in editable mode
#: from a checkout that is not under site-packages.
LIBRARY_PACKAGES = ("django", "nplus1_guard", "pytest", "_pytest", "sqlalchemy")


@dataclass(frozen=True)
class Origin:
    """Where a query came from, as far as the project is concerned."""

    filename: str
    lineno: int
    function: str

    def __str__(self) -> str:
        return f"{self.filename}:{self.lineno} in {self.function}()"

    @property
    def short(self) -> str:
        return f"{Path(self.filename).name}:{self.lineno}"


def _is_library(filename: str) -> bool:
    normalized = filename.replace("\\", "/")
    if any(marker in normalized for marker in LIBRARY_MARKERS):
        return True
    parts = normalized.split("/")
    return any(package in parts for package in LIBRARY_PACKAGES)


def find_origin(skip: int = 0) -> Origin | None:
    """Walk out of library code and report the first project frame.

    Returns ``None`` when there is no project frame at all, which happens for
    queries Django issues on its own behalf, such as during migrations.
    """
    frame: FrameType | None = sys._getframe(1 + skip)
    while frame is not None:
        filename = frame.f_code.co_filename
        if not _is_library(filename) and not filename.startswith("<"):
            return Origin(
                filename=filename,
                lineno=frame.f_lineno,
                function=frame.f_code.co_name,
            )
        frame = frame.f_back
    return None
