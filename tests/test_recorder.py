"""Recording queries, and finding the line that caused them."""

from __future__ import annotations

import pytest
from tests.testapp.models import Author, Book

from nplus1_guard import build_report, record

pytestmark = pytest.mark.django_db


class TestRecording:
    def test_it_records_with_debug_off(self, library: list[Author]) -> None:
        """connection.queries is empty when DEBUG is False; this must not be."""
        from django.conf import settings

        assert settings.DEBUG is False
        with record() as recorder:
            list(Author.objects.all())
        assert len(recorder) == 1

    def test_nothing_recorded_means_nothing_ran(self) -> None:
        with record() as recorder:
            pass
        assert len(recorder) == 0

    def test_a_queryset_is_not_a_query_until_it_is_evaluated(self) -> None:
        with record() as recorder:
            Author.objects.all()  # lazy on purpose
        assert len(recorder) == 0

    def test_transaction_statements_are_not_counted(self, db: None) -> None:
        from django.db import transaction

        with record() as recorder, transaction.atomic():
            Author.objects.count()
        assert len(recorder) == 1

    def test_each_query_carries_its_duration(self, library: list[Author]) -> None:
        with record() as recorder:
            list(Author.objects.all())
        assert recorder.total_duration >= 0
        assert all(query.duration >= 0 for query in recorder.queries)

    def test_recording_stops_at_the_end_of_the_block(
        self, library: list[Author]
    ) -> None:
        with record() as recorder:
            list(Author.objects.all())
        before = len(recorder)
        list(Author.objects.all())
        assert len(recorder) == before


class TestOrigin:
    def test_it_points_at_the_line_in_the_test_not_inside_django(
        self, library: list[Author]
    ) -> None:
        with record() as recorder:
            list(Author.objects.all())
        origin = recorder.queries[0].origin
        assert origin is not None
        assert origin.filename.replace("\\", "/").endswith("tests/test_recorder.py")
        assert "site-packages" not in origin.filename

    def test_the_origin_can_be_switched_off(self, library: list[Author]) -> None:
        with record(capture_origin=False) as recorder:
            list(Author.objects.all())
        assert recorder.queries[0].origin is None


class TestDetection:
    def test_a_loop_over_a_foreign_key_is_caught(self, library: list[Author]) -> None:
        with record() as recorder:
            for author in Author.objects.all():
                _ = author.publisher.name

        report = build_report(recorder.queries, threshold=3)
        assert report.has_nplus1
        assert report.total_queries == 11  # 1 for authors, 10 for publishers

        (duplicate,) = report.duplicates
        assert duplicate.count == 10
        assert "publisher" in duplicate.table

    def test_select_related_makes_it_go_away(self, library: list[Author]) -> None:
        with record() as recorder:
            for author in Author.objects.select_related("publisher"):
                _ = author.publisher.name

        report = build_report(recorder.queries, threshold=3)
        assert not report.has_nplus1
        assert report.total_queries == 1

    def test_a_reverse_relation_loop_is_caught(self, library: list[Author]) -> None:
        with record() as recorder:
            for author in Author.objects.all():
                _ = list(author.books.all())
        report = build_report(recorder.queries, threshold=3)
        assert report.has_nplus1

    def test_prefetch_related_makes_it_go_away(self, library: list[Author]) -> None:
        with record() as recorder:
            for author in Author.objects.prefetch_related("books"):
                _ = list(author.books.all())
        report = build_report(recorder.queries, threshold=3)
        assert not report.has_nplus1
        assert report.total_queries == 2  # authors, then all books in one go

    def test_the_threshold_is_respected(self, library: list[Author]) -> None:
        with record() as recorder:
            for author in Author.objects.all():
                _ = author.publisher.name
        assert build_report(recorder.queries, threshold=3).has_nplus1
        assert not build_report(recorder.queries, threshold=50).has_nplus1

    def test_distinct_queries_are_never_an_nplus1(self, library: list[Author]) -> None:
        """Ten different questions are not a loop, however many there are."""
        with record() as recorder:
            Author.objects.count()
            Book.objects.count()
            list(Author.objects.filter(name="Author 1"))
            list(Book.objects.filter(year=2020))
        assert not build_report(recorder.queries, threshold=1).has_nplus1
