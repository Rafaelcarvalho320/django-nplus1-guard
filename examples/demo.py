"""A self-contained demonstration.

    python examples/demo.py

Configures Django in memory, builds a small library, then runs the same piece
of work twice: once the way it gets written first, and once the way it gets
rewritten after someone looks at the query log.
"""

from __future__ import annotations

import django
from django.conf import settings

settings.configure(
    SECRET_KEY="demo",
    DEBUG=False,
    DATABASES={
        "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}
    },
    INSTALLED_APPS=["django.contrib.contenttypes", "django.contrib.auth", "__main__"],
    USE_TZ=True,
    DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
)
django.setup()

from django.db import connection, models  # noqa: E402

from nplus1_guard import build_report, record  # noqa: E402


class Publisher(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        app_label = "__main__"


class Author(models.Model):
    name = models.CharField(max_length=100)
    publisher = models.ForeignKey(
        Publisher, on_delete=models.CASCADE, related_name="authors"
    )

    class Meta:
        app_label = "__main__"


class Book(models.Model):
    title = models.CharField(max_length=200)
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="books")

    class Meta:
        app_label = "__main__"


def build_library(authors: int = 20, books_each: int = 3) -> None:
    with connection.schema_editor() as editor:
        for model in (Publisher, Author, Book):
            editor.create_model(model)

    publishers = [Publisher.objects.create(name=f"Publisher {n}") for n in range(3)]
    people = [
        Author.objects.create(name=f"Author {n}", publisher=publishers[n % 3])
        for n in range(authors)
    ]
    Book.objects.bulk_create(
        Book(title=f"Book {n}-{i}", author=author)
        for n, author in enumerate(people)
        for i in range(books_each)
    )


def catalogue_naive() -> list[str]:
    """How it gets written the first time."""
    lines = []
    for author in Author.objects.all():
        titles = ", ".join(book.title for book in author.books.all())
        lines.append(f"{author.name} ({author.publisher.name}): {titles}")
    return lines


def catalogue_fixed() -> list[str]:
    """The same output, after someone read the query log."""
    lines = []
    authors = Author.objects.select_related("publisher").prefetch_related("books")
    for author in authors:
        titles = ", ".join(book.title for book in author.books.all())
        lines.append(f"{author.name} ({author.publisher.name}): {titles}")
    return lines


def main() -> None:
    build_library()

    with record() as recorder:
        naive = catalogue_naive()
    naive_report = build_report(recorder.queries, threshold=5)

    with record() as recorder:
        fixed = catalogue_fixed()
    fixed_report = build_report(recorder.queries, threshold=5)

    assert naive == fixed, "the two versions must produce identical output"

    print("\n=== before: the obvious implementation ===\n")
    print(naive_report.format(label="catalogue_naive()"))

    print("\n\n=== after: select_related + prefetch_related ===\n")
    print(fixed_report.format(label="catalogue_fixed()"))

    saved = naive_report.total_queries - fixed_report.total_queries
    print(
        f"\n\nSame {len(naive)} lines of output, "
        f"{naive_report.total_queries} queries down to {fixed_report.total_queries} "
        f"({saved} fewer round trips)."
    )


if __name__ == "__main__":
    main()
