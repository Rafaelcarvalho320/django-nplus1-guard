"""Shared fixtures."""

from __future__ import annotations

import pytest
from tests.testapp.models import Author, Book, Publisher


@pytest.fixture
def library(db: None) -> list[Author]:
    """Ten authors across two publishers, three books each.

    Ten is chosen so that a per-author query is comfortably over any sensible
    threshold, and small enough that the suite stays fast.
    """
    publishers = [Publisher.objects.create(name=f"Publisher {n}") for n in range(2)]
    authors = [
        Author.objects.create(name=f"Author {n}", publisher=publishers[n % 2])
        for n in range(10)
    ]
    Book.objects.bulk_create(
        Book(title=f"Book {n}-{i}", author=author, year=2020 + i)
        for n, author in enumerate(authors)
        for i in range(3)
    )
    return authors


pytest_plugins = ["pytester"]
