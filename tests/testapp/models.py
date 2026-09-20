"""A deliberately ordinary schema: the shape every N+1 example uses."""

from django.db import models


class Publisher(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self) -> str:
        return self.name


class Author(models.Model):
    name = models.CharField(max_length=100)
    publisher = models.ForeignKey(
        Publisher, on_delete=models.CASCADE, related_name="authors"
    )

    def __str__(self) -> str:
        return self.name


class Book(models.Model):
    title = models.CharField(max_length=200)
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="books")
    year = models.PositiveSmallIntegerField(default=2026)

    def __str__(self) -> str:
        return self.title
