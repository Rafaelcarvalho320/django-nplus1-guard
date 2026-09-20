"""Reducing a SQL statement to its shape.

An N+1 is not "the same query ran twice", it is "the same query *shape* ran
once per row". These three statements are one shape:

    SELECT ... FROM book WHERE author_id = 1
    SELECT ... FROM book WHERE author_id = 2
    SELECT ... FROM book WHERE author_id = 3

Only the literal changes, so the detector has to compare statements with the
literals taken out. Everything below is about producing a stable key for that.
"""

from __future__ import annotations

import re

#: Quoted strings, including the doubled-quote escape form ('it''s').
_STRINGS = re.compile(r"'(?:[^']|'')*'")

#: Numbers, but only when standing alone, so that a column called "address2"
#: does not lose its 2 and collide with a column called "address".
_NUMBERS = re.compile(r"\b\d+\.?\d*\b")

#: Placeholders as the various drivers spell them: %s, ?, $1, :name.
_PLACEHOLDERS = re.compile(r"(%\([^)]*\)s|%s|\$\d+|:\w+|\?)")

#: An IN list of any length. Fetching 3 ids and fetching 300 is the same shape,
#: and treating them as different would hide a loop that grows with the data.
_IN_LIST = re.compile(r"\bIN\s*\(\s*(?:\?|\s|,)*\)", re.IGNORECASE)

_WHITESPACE = re.compile(r"\s+")

#: Statements that say nothing about query shape and would only add noise.
_NOISE = re.compile(
    r"^\s*(BEGIN|COMMIT|ROLLBACK|SAVEPOINT|RELEASE\s+SAVEPOINT|"
    r"ROLLBACK\s+TO\s+SAVEPOINT|SET\b|PRAGMA\b|SHOW\b)",
    re.IGNORECASE,
)


def is_noise(sql: str) -> bool:
    """True for transaction and session statements, which are not queries."""
    return bool(_NOISE.match(sql))


def fingerprint(sql: str) -> str:
    """A stable key for the shape of ``sql``.

    Literals become ``?``, IN lists collapse to ``IN (?)``, whitespace is
    normalized and the result is upper-cased. Two statements that differ only
    in their parameters end up with the same fingerprint.
    """
    shaped = _STRINGS.sub("?", sql)
    shaped = _PLACEHOLDERS.sub("?", shaped)
    shaped = _NUMBERS.sub("?", shaped)
    shaped = _IN_LIST.sub("IN (?)", shaped)
    shaped = _WHITESPACE.sub(" ", shaped).strip()
    return shaped.upper()


def summarize(sql: str, width: int = 100) -> str:
    """A one-line version of a statement, for reports."""
    collapsed = _WHITESPACE.sub(" ", sql).strip()
    if len(collapsed) <= width:
        return collapsed
    return collapsed[: width - 3] + "..."


_TABLE = re.compile(
    r'\bFROM\s+["`\[]?(\w+)["`\]]?|\bINTO\s+["`\[]?(\w+)["`\]]?|'
    r'\bUPDATE\s+["`\[]?(\w+)["`\]]?',
    re.IGNORECASE,
)


def table_of(sql: str) -> str:
    """Best-effort table name, used to label a group of queries.

    Deliberately a regex and not a SQL parser. Getting the label wrong on an
    exotic statement costs a slightly worse report; adding a parser dependency
    to a development-only tool costs every user of the library forever.
    """
    match = _TABLE.search(sql)
    if not match:
        return "?"
    return next((group for group in match.groups() if group), "?")
