"""Grouping, ranking and wording of the report."""

from __future__ import annotations

from nplus1_guard.origin import Origin
from nplus1_guard.recorder import Query
from nplus1_guard.report import build_report


def query(sql: str, *, duration: float = 0.001, origin: Origin | None = None) -> Query:
    from nplus1_guard.fingerprint import fingerprint

    return Query(
        sql=sql,
        alias="default",
        duration=duration,
        fingerprint=fingerprint(sql),
        origin=origin,
    )


def loop(count: int, *, table: str = "book", origin: Origin | None = None):
    return [
        query(f"SELECT * FROM {table} WHERE author_id = {n}", origin=origin)
        for n in range(count)
    ]


class TestGrouping:
    def test_a_repeated_shape_becomes_one_group(self) -> None:
        report = build_report(loop(10), threshold=3)
        (duplicate,) = report.duplicates
        assert duplicate.count == 10

    def test_exactly_at_the_threshold_is_not_a_problem(self) -> None:
        """The threshold is "more than", so it is an upper bound you may hit."""
        assert not build_report(loop(3), threshold=3).has_nplus1
        assert build_report(loop(4), threshold=3).has_nplus1

    def test_groups_are_ranked_worst_first(self) -> None:
        report = build_report(
            loop(5, table="book") + loop(20, table="tag"), threshold=2
        )
        assert [d.count for d in report.duplicates] == [20, 5]

    def test_the_durations_of_a_group_are_summed(self) -> None:
        queries = [
            query("SELECT 1 FROM t WHERE a = 1", duration=0.01) for _ in range(4)
        ]
        (duplicate,) = build_report(queries, threshold=2).duplicates
        assert duplicate.total_duration == 0.04


class TestWording:
    def test_a_clean_report_says_so(self) -> None:
        assert "no repeated query shapes" in build_report(loop(2), threshold=5).format()

    def test_the_report_names_the_table_and_the_count(self) -> None:
        text = build_report(loop(10), threshold=3).format()
        assert "10x on `book`" in text

    def test_the_report_points_at_the_offending_line(self) -> None:
        origin = Origin(filename="/app/views.py", lineno=42, function="list_books")
        text = build_report(loop(10, origin=origin), threshold=3).format()
        assert "/app/views.py:42 in list_books()" in text

    def test_it_says_how_many_queries_were_avoidable(self) -> None:
        text = build_report(loop(10), threshold=3).format()
        assert "9 of the 10 queries look avoidable" in text

    def test_it_suggests_the_actual_fix(self) -> None:
        text = build_report(loop(10), threshold=3).format()
        assert "select_related" in text
        assert "prefetch_related" in text

    def test_the_label_appears_in_the_header(self) -> None:
        assert "GET /books/" in build_report(loop(10), threshold=3).format(
            label="GET /books/"
        )

    def test_a_group_with_several_origins_shows_the_busiest_first(self) -> None:
        hot = Origin("/app/views.py", 10, "hot")
        cold = Origin("/app/views.py", 99, "cold")
        report = build_report(loop(9, origin=hot) + loop(2, origin=cold), threshold=3)
        (duplicate,) = report.duplicates
        assert duplicate.main_origin == hot
        assert "also /app/views.py:99 in cold() (2x)" in duplicate.describe()


class TestTotals:
    def test_totals_cover_every_query_not_only_the_duplicates(self) -> None:
        report = build_report([*loop(10), query("SELECT 1 FROM author")], threshold=3)
        assert report.total_queries == 11
        assert report.duplicates[0].count == 10

    def test_an_empty_recording_is_clean(self) -> None:
        report = build_report([], threshold=3)
        assert not report.has_nplus1
        assert report.total_queries == 0
        assert "0 queries" in report.format()

    def test_one_query_is_not_pluralised(self) -> None:
        assert "1 query " in build_report([query("SELECT 1 FROM t")]).format()
