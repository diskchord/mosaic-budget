from __future__ import annotations

from datetime import UTC, date, datetime

from app.services.sync import _effective_date, _epoch_to_datetime, next_scheduled_at


def test_schedule_uses_stable_nonround_minute() -> None:
    now = datetime(2026, 8, 27, 14, 0, tzinfo=UTC)
    assert next_scheduled_at(now, 180, 17) == datetime(2026, 8, 27, 15, 17, tzinfo=UTC)
    assert next_scheduled_at(datetime(2026, 8, 27, 15, 17, tzinfo=UTC), 180, 17) == datetime(
        2026, 8, 27, 18, 17, tzinfo=UTC
    )


def test_invalid_or_zero_epoch_is_pending_without_posted_time() -> None:
    assert _epoch_to_datetime(0) is None
    assert _epoch_to_datetime("bad") is None


def test_effective_date_prefers_transacted_time() -> None:
    posted = datetime(2026, 8, 28, 1, 0, tzinfo=UTC)
    transacted = datetime(2026, 8, 27, 20, 0, tzinfo=UTC)
    assert _effective_date(posted, transacted) == date(2026, 8, 27)
