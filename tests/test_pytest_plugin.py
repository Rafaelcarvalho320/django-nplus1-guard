"""The pytest plugin: fixtures, marker and command line options."""

from __future__ import annotations

import pytest
from tests.testapp.models import Author

pytestmark = pytest.mark.django_db


class TestGuardFixture:
    def test_it_fails_the_test_when_a_loop_is_detected(
        self, assert_no_nplus1, library: list[Author]
    ) -> None:
        with pytest.raises(pytest.fail.Exception), assert_no_nplus1(threshold=3):
            for author in Author.objects.all():
                _ = author.publisher.name

    def test_it_stays_quiet_when_the_query_is_already_optimal(
        self, assert_no_nplus1, library: list[Author]
    ) -> None:
        with assert_no_nplus1(threshold=3):
            for author in Author.objects.select_related("publisher"):
                _ = author.publisher.name

    def test_the_failure_message_names_the_table_and_the_count(
        self, assert_no_nplus1, library: list[Author]
    ) -> None:
        with (
            pytest.raises(pytest.fail.Exception) as excinfo,
            assert_no_nplus1(threshold=3, label="serializing authors"),
        ):
            for author in Author.objects.all():
                _ = author.publisher.name
        message = str(excinfo.value)
        assert "serializing authors" in message
        assert "10x on" in message
        assert "select_related" in message

    def test_it_guards_only_the_block_it_wraps(
        self, assert_no_nplus1, library: list[Author]
    ) -> None:
        for author in Author.objects.all():
            _ = author.publisher.name  # outside the guard, so it does not count
        with assert_no_nplus1(threshold=3):
            list(Author.objects.all())


class TestReportFixture:
    def test_it_hands_back_the_numbers_instead_of_judging(
        self, nplus1_report, library: list[Author]
    ) -> None:
        with nplus1_report(threshold=3) as holder:
            for author in Author.objects.all():
                _ = author.publisher.name
        (report,) = holder
        assert report.total_queries == 11
        assert report.duplicates[0].count == 10

    def test_it_can_prove_a_fix_actually_worked(
        self, nplus1_report, library: list[Author]
    ) -> None:
        """The shape of a regression test for a performance fix."""
        with nplus1_report() as before:
            for author in Author.objects.all():
                _ = author.publisher.name
        with nplus1_report() as after:
            for author in Author.objects.select_related("publisher"):
                _ = author.publisher.name

        assert before[0].total_queries == 11
        assert after[0].total_queries == 1
        assert not after[0].has_nplus1
