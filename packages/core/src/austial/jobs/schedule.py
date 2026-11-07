"""Cron-schedule parsing without a third-party dependency.

Supports:

- ``"@hourly"`` -- top of every hour (``0 * * * *``).
- ``"@daily"`` -- midnight UTC (``0 0 * * *``).
- ``"@weekly"`` -- midnight UTC Sunday.
- ``"@monthly"`` -- midnight UTC on the 1st.
- ``"@every <N>s|m|h"`` -- fixed offset from the previous run.
- Standard 5-field cron: ``minute hour day-of-month month day-of-week``.
  Each field accepts ``*``, ``N``, ``A-B``, ``*/N`` and comma-separated combos.

Enough for scheduled jobs in a fintech backend; croniter can be swapped in
by a product that needs the exotic corners of cron syntax. Documented in the
docs page for this package.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from austial.jobs.errors import InvalidScheduleError


@dataclass(frozen=True, slots=True)
class Schedule:
    """A parsed schedule. ``next_run_at(after)`` yields the next fire time strictly
    after ``after`` (aligned to whole seconds for cron; exact offset for ``@every``)."""

    raw: str
    _fixed_interval: timedelta | None
    _minutes: frozenset[int]
    _hours: frozenset[int]
    _days: frozenset[int]
    _months: frozenset[int]
    _dows: frozenset[int]

    def next_run_at(self, after: datetime) -> datetime:
        after = after if after.tzinfo else after.replace(tzinfo=UTC)
        if self._fixed_interval is not None:
            return after + self._fixed_interval

        # Cron: advance minute-by-minute until every field matches. Bounded at
        # 4 years to avoid infinite loops on impossible specs like Feb 30.
        candidate = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
        limit = candidate + timedelta(days=366 * 4)
        while candidate < limit:
            if (
                candidate.minute in self._minutes
                and candidate.hour in self._hours
                and candidate.day in self._days
                and candidate.month in self._months
                and (candidate.weekday() + 1) % 7 in self._dows  # Mon=1..Sun=0 in cron
            ):
                return candidate
            candidate += timedelta(minutes=1)
        raise InvalidScheduleError(self.raw, "no matching time within 4 years")


_FULL_MINUTES = frozenset(range(60))
_FULL_HOURS = frozenset(range(24))
_FULL_DAYS = frozenset(range(1, 32))
_FULL_MONTHS = frozenset(range(1, 13))
_FULL_DOWS = frozenset(range(7))


def _parse_field(spec: str, lo: int, hi: int, whole: frozenset[int]) -> frozenset[int]:
    if spec == "*":
        return whole
    values: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        step = 1
        if "/" in part:
            base, step_str = part.split("/", 1)
            step = int(step_str)
            if step <= 0:
                raise InvalidScheduleError(spec, "step must be positive")
        else:
            base = part
        if base == "*" or base == "":
            start, end = lo, hi
        elif "-" in base:
            a, b = base.split("-", 1)
            start, end = int(a), int(b)
        else:
            start = end = int(base)
        for v in range(start, end + 1, step):
            if v < lo or v > hi:
                raise InvalidScheduleError(spec, f"value {v} out of range [{lo},{hi}]")
            values.add(v)
    if not values:
        raise InvalidScheduleError(spec, "no values selected")
    return frozenset(values)


def _parse_every(spec: str) -> timedelta:
    body = spec[len("@every ") :].strip()
    if not body:
        raise InvalidScheduleError(spec, "missing interval")
    unit = body[-1]
    try:
        amount = int(body[:-1])
    except ValueError as exc:
        raise InvalidScheduleError(spec, "amount must be an integer") from exc
    if amount <= 0:
        raise InvalidScheduleError(spec, "interval must be positive")
    if unit == "s":
        return timedelta(seconds=amount)
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "h":
        return timedelta(hours=amount)
    raise InvalidScheduleError(spec, "unit must be one of s/m/h")


_SHORTHAND: dict[str, str] = {
    "@hourly": "0 * * * *",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@weekly": "0 0 * * 0",
    "@monthly": "0 0 1 * *",
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
}


def parse_schedule(schedule: str) -> Schedule:
    """Turn a schedule string into a :class:`Schedule`. Raises
    :class:`InvalidScheduleError` on malformed input."""

    if not schedule or not schedule.strip():
        raise InvalidScheduleError(schedule, "empty")
    raw = schedule.strip()

    if raw.startswith("@every "):
        return Schedule(
            raw=raw,
            _fixed_interval=_parse_every(raw),
            _minutes=frozenset(),
            _hours=frozenset(),
            _days=frozenset(),
            _months=frozenset(),
            _dows=frozenset(),
        )

    if raw in _SHORTHAND:
        raw = _SHORTHAND[raw]

    fields = raw.split()
    if len(fields) != 5:
        raise InvalidScheduleError(schedule, "expected 5-field cron")
    minutes = _parse_field(fields[0], 0, 59, _FULL_MINUTES)
    hours = _parse_field(fields[1], 0, 23, _FULL_HOURS)
    days = _parse_field(fields[2], 1, 31, _FULL_DAYS)
    months = _parse_field(fields[3], 1, 12, _FULL_MONTHS)
    dows = _parse_field(fields[4], 0, 6, _FULL_DOWS)
    return Schedule(
        raw=schedule.strip(),
        _fixed_interval=None,
        _minutes=minutes,
        _hours=hours,
        _days=days,
        _months=months,
        _dows=dows,
    )
