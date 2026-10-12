"""Group dated expenses into trips / periods by date proximity."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass, field

GAP_DAYS = 3  # a gap longer than this starts a new group


@dataclass
class Group:
    id: str
    start: dt.date
    end: dt.date
    files: list[str] = field(default_factory=list)

    @property
    def title(self) -> str:
        if self.start == self.end:
            return f"Expenses on {self.start:%d %b %Y}"
        return f"Expenses {self.start:%d %b} – {self.end:%d %b %Y}"


def group_by_date(items: Sequence[tuple[str, dt.date]], gap_days: int = GAP_DAYS) -> list[Group]:
    groups: list[Group] = []
    for file, date in sorted(items, key=lambda x: (x[1], x[0])):
        if groups and (date - groups[-1].end).days <= gap_days:
            groups[-1].end = date
            groups[-1].files.append(file)
        else:
            groups.append(Group(id=f"g-{date.isoformat()}", start=date, end=date, files=[file]))
    return groups
