"""pytest plugin: turn an N+1 into a failing test.

Three ways in, from narrowest to widest:

    def test_one(assert_no_nplus1):          # guard a block
        with assert_no_nplus1(threshold=2):
            view_logic()

    @pytest.mark.nplus1(threshold=3)         # guard a whole test
    def test_two(): ...

    pytest --nplus1                          # guard every test

``--nplus1-report`` is the read-only version: it prints the worst offenders at
the end of the run without failing anything, which is how you find out how bad
things already are before turning the gate on.
"""

from __future__ import annotations

from collections.abc import Generator, Iterator
from typing import Any

import pytest

from nplus1_guard.recorder import record
from nplus1_guard.report import DEFAULT_THRESHOLD, Report, build_report

_COLLECTED: list[tuple[str, Report]] = []


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("nplus1", "N+1 query detection")
    group.addoption(
        "--nplus1",
        action="store_true",
        default=False,
        help="Fail any test whose queries look like an N+1.",
    )
    group.addoption(
        "--nplus1-report",
        action="store_true",
        default=False,
        help="Report N+1 suspects at the end of the run without failing.",
    )
    group.addoption(
        "--nplus1-threshold",
        type=int,
        default=DEFAULT_THRESHOLD,
        metavar="N",
        help=(
            f"More than N of one query shape is an N+1 (default: {DEFAULT_THRESHOLD})."
        ),
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "nplus1(threshold=N): fail this test if one query shape runs more than "
        "N times. Threshold defaults to --nplus1-threshold.",
    )


def _django_is_ready() -> bool:
    """The plugin is installed globally; not every suite is a Django suite."""
    try:
        from django.conf import settings
    except ImportError:
        return False
    return bool(settings.configured)


def _threshold_for(item: pytest.Item) -> int | None:
    """The threshold to apply to this test, or None to leave it alone."""
    default = int(item.config.getoption("--nplus1-threshold"))
    marker = item.get_closest_marker("nplus1")
    if marker is not None:
        return int(marker.kwargs.get("threshold", default))
    if item.config.getoption("--nplus1") or item.config.getoption("--nplus1-report"):
        return default
    return None


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None, Any, Any]:
    threshold = _threshold_for(item)
    if threshold is None or not _django_is_ready():
        return (yield)

    with record() as recorder:
        # If the test itself fails, this raises and the N+1 check never runs.
        # Reporting a query pattern on top of an already-failing test would
        # only bury the real error.
        result = yield

    report = build_report(recorder.queries, threshold=threshold)
    if report.has_nplus1:
        _COLLECTED.append((item.nodeid, report))
        if item.config.getoption("--nplus1") or item.get_closest_marker("nplus1"):
            pytest.fail(report.format(label=item.nodeid), pytrace=False)
    return result


def pytest_terminal_summary(terminalreporter: Any) -> None:
    if not _COLLECTED:
        return
    terminalreporter.write_sep("=", "N+1 suspects")
    for nodeid, report in sorted(
        _COLLECTED, key=lambda pair: pair[1].duplicates[0].count, reverse=True
    ):
        worst = report.duplicates[0]
        location = worst.main_origin.short if worst.main_origin else "unknown"
        terminalreporter.write_line(
            f"  {worst.count:4d}x on `{worst.table}` at {location}   {nodeid}"
        )
    _COLLECTED.clear()


@pytest.fixture
def assert_no_nplus1() -> Iterator[Any]:
    """Guard one block of a test rather than the whole thing.

    with assert_no_nplus1(threshold=2):
        serialize(queryset)
    """
    from contextlib import contextmanager

    @contextmanager
    def guard(threshold: int = DEFAULT_THRESHOLD, label: str = "") -> Iterator[None]:
        with record() as recorder:
            yield
        report = build_report(recorder.queries, threshold=threshold)
        if report.has_nplus1:
            pytest.fail(report.format(label=label), pytrace=False)

    yield guard


@pytest.fixture
def nplus1_report() -> Iterator[Any]:
    """Record a block and hand back the report, without judging it.

    For tests that want to assert on the numbers themselves, such as proving
    that a fix took a query count from 21 down to 2.
    """
    from contextlib import contextmanager

    @contextmanager
    def capture(threshold: int = DEFAULT_THRESHOLD) -> Iterator[list[Report]]:
        holder: list[Report] = []
        with record() as recorder:
            yield holder
        holder.append(build_report(recorder.queries, threshold=threshold))

    yield capture
