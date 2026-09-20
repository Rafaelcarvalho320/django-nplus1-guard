"""Reducing SQL to a shape."""

from __future__ import annotations

import pytest

from nplus1_guard.fingerprint import fingerprint, is_noise, summarize, table_of


class TestFingerprint:
    def test_the_same_query_with_different_ids_is_one_shape(self) -> None:
        """This is the entire premise of the detector."""
        a = fingerprint("SELECT id FROM book WHERE author_id = 1")
        b = fingerprint("SELECT id FROM book WHERE author_id = 2")
        assert a == b

    def test_placeholders_and_literals_agree(self) -> None:
        """Parameterised and inlined forms of one query must not split."""
        assert fingerprint("SELECT * FROM t WHERE a = %s") == fingerprint(
            "SELECT * FROM t WHERE a = 7"
        )

    def test_different_tables_are_different_shapes(self) -> None:
        assert fingerprint("SELECT * FROM book") != fingerprint("SELECT * FROM author")

    def test_different_columns_are_different_shapes(self) -> None:
        assert fingerprint("SELECT * FROM t WHERE a = 1") != fingerprint(
            "SELECT * FROM t WHERE b = 1"
        )

    def test_string_literals_are_erased(self) -> None:
        assert fingerprint("SELECT * FROM t WHERE name = 'ana'") == fingerprint(
            "SELECT * FROM t WHERE name = 'bruno'"
        )

    def test_an_escaped_quote_does_not_break_the_scan(self) -> None:
        shaped = fingerprint("SELECT * FROM t WHERE name = 'it''s' AND id = 1")
        assert "IT''S" not in shaped

    def test_in_lists_of_any_length_are_one_shape(self) -> None:
        """Fetching 3 ids and 300 is the same code; only the data grew."""
        assert fingerprint("SELECT * FROM t WHERE id IN (%s, %s)") == fingerprint(
            "SELECT * FROM t WHERE id IN (%s, %s, %s, %s, %s)"
        )

    def test_whitespace_and_case_do_not_matter(self) -> None:
        assert fingerprint("select  *\n from   t") == fingerprint("SELECT * FROM t")

    def test_a_digit_inside_an_identifier_is_kept(self) -> None:
        """Otherwise address2 and address would collide into one shape."""
        assert fingerprint("SELECT address2 FROM t") != fingerprint(
            "SELECT address FROM t"
        )


class TestNoise:
    @pytest.mark.parametrize(
        "sql",
        [
            "BEGIN",
            "COMMIT",
            "ROLLBACK",
            "SAVEPOINT s1",
            "RELEASE SAVEPOINT s1",
            "  PRAGMA foreign_keys = ON",
            "SET search_path TO public",
        ],
    )
    def test_transaction_statements_are_not_queries(self, sql: str) -> None:
        assert is_noise(sql)

    @pytest.mark.parametrize(
        "sql", ["SELECT 1", "INSERT INTO t VALUES (1)", "UPDATE t SET a = 1"]
    )
    def test_real_statements_are_not_noise(self, sql: str) -> None:
        assert not is_noise(sql)


class TestLabels:
    @pytest.mark.parametrize(
        ("sql", "table"),
        [
            ("SELECT * FROM book WHERE id = 1", "book"),
            ('SELECT * FROM "testapp_book"', "testapp_book"),
            ("INSERT INTO author (name) VALUES (1)", "author"),
            ("UPDATE author SET name = 1", "author"),
        ],
    )
    def test_the_table_is_picked_out_for_the_report(self, sql: str, table: str) -> None:
        assert table_of(sql) == table

    def test_an_unrecognised_statement_gets_a_placeholder(self) -> None:
        assert table_of("WITH x AS (SELECT 1) SELECT 1") == "?"

    def test_long_statements_are_truncated(self) -> None:
        assert summarize("SELECT " + "a, " * 200 + "b FROM t", width=40).endswith("...")

    def test_short_statements_are_left_alone(self) -> None:
        assert summarize("SELECT 1 FROM t") == "SELECT 1 FROM t"
