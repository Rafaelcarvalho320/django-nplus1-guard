"""Recording the queries that run inside a block of code.

Built on ``connection.execute_wrapper``, which is Django's supported hook and,
unlike reading ``connection.queries``, works with ``DEBUG = False``. That
matters: the whole point is to run this in tests and in CI, where DEBUG is off,
and ``connection.queries`` is empty there.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from typing import Any

from django.db import connections

from nplus1_guard.fingerprint import fingerprint, is_noise
from nplus1_guard.origin import Origin, find_origin


@dataclass(frozen=True)
class Query:
    """One executed statement."""

    sql: str
    alias: str
    duration: float
    fingerprint: str
    origin: Origin | None


@dataclass
class Recorder:
    """Collects queries. Instances are reusable but not thread-safe."""

    queries: list[Query] = field(default_factory=list)
    capture_origin: bool = True

    def __len__(self) -> int:
        return len(self.queries)

    @property
    def total_duration(self) -> float:
        return sum(query.duration for query in self.queries)

    def wrapper(self, alias: str) -> Callable[..., Any]:
        def execute_wrapper(
            execute: Callable[..., Any],
            sql: str,
            params: Sequence[Any] | None,
            many: bool,
            context: dict[str, Any],
        ) -> Any:
            if is_noise(sql):
                # Still has to be executed; just not counted as a query shape.
                return execute(sql, params, many, context)
            started = time.perf_counter()
            try:
                return execute(sql, params, many, context)
            finally:
                self.queries.append(
                    Query(
                        sql=sql,
                        alias=alias,
                        duration=time.perf_counter() - started,
                        fingerprint=fingerprint(sql),
                        # Recorded even when the query raises: a statement that
                        # blows up is exactly the one you want located.
                        origin=find_origin(skip=1) if self.capture_origin else None,
                    )
                )

        return execute_wrapper


@contextmanager
def record(
    using: str | Sequence[str] | None = None, capture_origin: bool = True
) -> Iterator[Recorder]:
    """Record every query run inside the block.

    ``using`` defaults to every configured connection, because an N+1 that only
    shows up against the replica is still an N+1.
    """
    if using is None:
        aliases = list(connections)
    elif isinstance(using, str):
        aliases = [using]
    else:
        aliases = list(using)

    recorder = Recorder(capture_origin=capture_origin)
    with ExitStack() as stack:
        for alias in aliases:
            connection = connections[alias]
            stack.enter_context(connection.execute_wrapper(recorder.wrapper(alias)))
        yield recorder
