"""Middleware that watches a request for N+1 queries.

Placed as high in the stack as possible, so it sees the queries every other
middleware makes too. It never changes the response body; the worst it does is
add a header, log a warning, or — if you ask for it — raise.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest, HttpResponse

from nplus1_guard.conf import get_config
from nplus1_guard.recorder import record
from nplus1_guard.report import Report, build_report

log = logging.getLogger("nplus1_guard")

HEADER_NAME = "X-NPlusOne-Queries"


class NPlusOneDetected(Exception):
    """Raised, when configured to, instead of only logging.

    Deliberately loud. A performance bug that only ever writes a line to a log
    nobody reads is a performance bug that ships.
    """

    def __init__(self, report: Report, path: str) -> None:
        self.report = report
        self.path = path
        super().__init__(f"\n{report.format(label=path)}")


class NPlusOneMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        # Fail at startup rather than at the first request: a middleware that
        # silently does nothing is worse than one that refuses to load.
        if not callable(get_response):
            raise ImproperlyConfigured("NPlusOneMiddleware needs a response handler")

    def __call__(self, request: HttpRequest) -> HttpResponse:
        config = get_config()
        if not config.enabled or config.path_ignored(request.path):
            return self.get_response(request)

        with record() as recorder:
            response = self.get_response(request)

        report = build_report(recorder.queries, threshold=config.threshold)
        if config.header:
            response[HEADER_NAME] = str(report.total_queries)

        duplicates = [
            duplicate
            for duplicate in report.duplicates
            if not config.table_ignored(duplicate.table)
        ]
        if not duplicates:
            return response

        if config.raise_on_detection:
            raise NPlusOneDetected(report, request.path)

        log.log(
            logging.getLevelName(config.log_level),
            "%s %s: %s",
            request.method,
            request.path,
            report.format(label=f"{request.method} {request.path}"),
        )
        return response
