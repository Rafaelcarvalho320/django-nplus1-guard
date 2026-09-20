"""Two views over the same data: one that loops, one that does not."""

from django.http import HttpRequest, HttpResponse
from tests.testapp.models import Author


def naive(request: HttpRequest) -> HttpResponse:
    """One extra query per author, which is the whole problem."""
    lines = [
        f"{author.name} / {author.publisher.name}" for author in Author.objects.all()
    ]
    return HttpResponse("\n".join(lines))


def optimized(request: HttpRequest) -> HttpResponse:
    """The same output, in a single join."""
    authors = Author.objects.select_related("publisher")
    lines = [f"{author.name} / {author.publisher.name}" for author in authors]
    return HttpResponse("\n".join(lines))


def health(request: HttpRequest) -> HttpResponse:
    return HttpResponse("ok")
