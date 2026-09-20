"""Turning recorded queries into a verdict.

The rule is deliberately simple: group by fingerprint, and any shape that ran
more than the threshold is a suspected N+1. Simple is the point. A detector
with clever heuristics is a detector nobody trusts when it stays quiet.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from nplus1_guard.fingerprint import summarize, table_of
from nplus1_guard.origin import Origin
from nplus1_guard.recorder import Query

DEFAULT_THRESHOLD = 5


@dataclass(frozen=True)
class Duplicate:
    """One query shape that ran more times than the threshold allows."""

    fingerprint: str
    count: int
    sample_sql: str
    total_duration: float
    origins: tuple[tuple[Origin, int], ...]

    @property
    def table(self) -> str:
        return table_of(self.sample_sql)

    @property
    def main_origin(self) -> Origin | None:
        return self.origins[0][0] if self.origins else None

    def describe(self, width: int = 100) -> str:
        head = (
            f"{self.count}x on `{self.table}` "
            f"({self.total_duration * 1000:.1f} ms total)"
        )
        lines = [head]
        if self.main_origin is not None:
            lines.append(f"    from {self.main_origin}")
            for origin, count in self.origins[1:3]:
                lines.append(f"    also {origin} ({count}x)")
        lines.append(f"    {summarize(self.sample_sql, width)}")
        return "\n".join(lines)


@dataclass
class Report:
    """What a recording found."""

    queries: list[Query]
    threshold: int = DEFAULT_THRESHOLD

    @property
    def total_queries(self) -> int:
        return len(self.queries)

    @property
    def total_duration(self) -> float:
        return sum(query.duration for query in self.queries)

    @property
    def duplicates(self) -> list[Duplicate]:
        """Query shapes that ran more than ``threshold`` times, worst first."""
        grouped: dict[str, list[Query]] = {}
        for query in self.queries:
            grouped.setdefault(query.fingerprint, []).append(query)

        found = [
            _build(shape, group)
            for shape, group in grouped.items()
            if len(group) > self.threshold
        ]
        return sorted(found, key=lambda d: d.count, reverse=True)

    @property
    def has_nplus1(self) -> bool:
        return bool(self.duplicates)

    def format(self, label: str = "") -> str:
        header = f"N+1 report{': ' + label if label else ''}"
        lines = [
            header,
            "-" * max(len(header), 60),
            f"  {self.total_queries} quer{'y' if self.total_queries == 1 else 'ies'}"
            f" in {self.total_duration * 1000:.1f} ms"
            f"  (threshold: more than {self.threshold} of one shape)",
        ]
        if not self.duplicates:
            lines.append("  no repeated query shapes")
            return "\n".join(lines)

        lines.append("")
        for index, duplicate in enumerate(self.duplicates, start=1):
            lines.append(f"  [{index}] {duplicate.describe()}")
            lines.append("")
        wasted = sum(d.count - 1 for d in self.duplicates)
        lines.append(f"  {wasted} of the {self.total_queries} queries look avoidable.")
        lines.append(
            "  Usual fix: select_related() for forward FK/one-to-one, "
            "prefetch_related() for reverse and many-to-many."
        )
        return "\n".join(lines)


def _build(shape: str, group: Sequence[Query]) -> Duplicate:
    counts: dict[Origin, int] = {}
    for query in group:
        if query.origin is not None:
            counts[query.origin] = counts.get(query.origin, 0) + 1
    ranked = tuple(sorted(counts.items(), key=lambda item: item[1], reverse=True))
    return Duplicate(
        fingerprint=shape,
        count=len(group),
        sample_sql=group[0].sql,
        total_duration=sum(query.duration for query in group),
        origins=ranked,
    )


def build_report(
    queries: Iterable[Query], threshold: int = DEFAULT_THRESHOLD
) -> Report:
    return Report(queries=list(queries), threshold=threshold)
