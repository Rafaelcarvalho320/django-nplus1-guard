"""The marker and the command line options, driven through a real pytest run.

These spawn a nested pytest against a throwaway Django project, because the
behaviour under test is "does the run fail", which cannot be asserted from
inside the run that is being tested.

The nested run configures Django itself and turns pytest-django off, so it does
not inherit this project's settings module and try to import it from a
temporary directory.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

CONFTEST = '''
import django
from django.conf import settings

settings.configure(
    SECRET_KEY="x",
    DEBUG=False,
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
    INSTALLED_APPS=["django.contrib.contenttypes", "django.contrib.auth"],
    USE_TZ=True,
)
django.setup()

import pytest
from django.test.runner import DiscoverRunner
from django.test.utils import setup_test_environment, teardown_test_environment


@pytest.fixture(scope="session")
def database():
    setup_test_environment()
    runner = DiscoverRunner(verbosity=0)
    old_config = runner.setup_databases()
    yield
    runner.teardown_databases(old_config)
    teardown_test_environment()


@pytest.fixture
def people(database):
    """Ten users in one group, rolled back after each test."""
    from django.contrib.auth.models import Group, User
    from django.db import transaction

    atomic = transaction.atomic()
    atomic.__enter__()
    group = Group.objects.create(name="staff")
    for n in range(10):
        User.objects.create(username=f"u{n}").groups.add(group)
    yield
    transaction.set_rollback(True)
    atomic.__exit__(None, None, None)
'''

LOOPING_TEST = """
from django.contrib.auth.models import User


def test_loops(people):
    for user in User.objects.all():
        list(user.groups.all())
"""

Runner = Callable[..., pytest.RunResult]


@pytest.fixture
def run(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> Runner:
    """Run a nested pytest with a clean Django environment."""
    monkeypatch.delenv("DJANGO_SETTINGS_MODULE", raising=False)
    pytester.makeconftest(CONFTEST)

    def runner(*args: str, **files: str) -> pytest.RunResult:
        if files:
            pytester.makepyfile(**files)
        return pytester.runpytest_subprocess(
            "-p", "no:django", "-p", "no:cacheprovider", *args
        )

    return runner


class TestCommandLine:
    def test_without_the_flag_a_looping_test_still_passes(self, run: Runner) -> None:
        """The plugin is installed globally and must stay out of the way."""
        run(test_loop=LOOPING_TEST).assert_outcomes(passed=1)

    def test_the_flag_turns_a_loop_into_a_failure(self, run: Runner) -> None:
        result = run("--nplus1", "--nplus1-threshold", "3", test_loop=LOOPING_TEST)
        result.assert_outcomes(failed=1)
        result.stdout.fnmatch_lines(["*10x on*"])

    def test_a_generous_threshold_lets_it_pass(self, run: Runner) -> None:
        run(
            "--nplus1", "--nplus1-threshold", "100", test_loop=LOOPING_TEST
        ).assert_outcomes(passed=1)

    def test_report_mode_warns_without_failing(self, run: Runner) -> None:
        """How you find out how bad it already is, before turning the gate on."""
        result = run(
            "--nplus1-report", "--nplus1-threshold", "3", test_loop=LOOPING_TEST
        )
        result.assert_outcomes(passed=1)
        result.stdout.fnmatch_lines(["*N+1 suspects*"])


class TestMarker:
    def test_the_marker_guards_one_test_and_leaves_the_others(
        self, run: Runner
    ) -> None:
        result = run(
            test_marked="""
import pytest
from django.contrib.auth.models import User


@pytest.mark.nplus1(threshold=3)
def test_guarded(people):
    for user in User.objects.all():
        list(user.groups.all())


def test_unguarded(people):
    for user in User.objects.all():
        list(user.groups.all())
"""
        )
        result.assert_outcomes(passed=1, failed=1)

    def test_a_failing_test_is_not_buried_under_an_nplus1_report(
        self, run: Runner
    ) -> None:
        """The real assertion error has to survive, not be replaced by ours."""
        result = run(
            test_broken="""
import pytest
from django.contrib.auth.models import User


@pytest.mark.nplus1(threshold=3)
def test_broken(people):
    for user in User.objects.all():
        list(user.groups.all())
    assert 1 == 2, "the real failure"
"""
        )
        result.assert_outcomes(failed=1)
        result.stdout.fnmatch_lines(["*the real failure*"])

    def test_a_marked_test_with_no_loop_passes(self, run: Runner) -> None:
        result = run(
            test_clean="""
import pytest
from django.contrib.auth.models import User


@pytest.mark.nplus1(threshold=3)
def test_clean(people):
    list(User.objects.prefetch_related("groups"))
"""
        )
        result.assert_outcomes(passed=1)
