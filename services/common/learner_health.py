"""Is every SA learner still fitting? (Timeline "Parallel capture track", stale-fit alert.)

`sa-learner` wraps every nightly fit in a try/except that only logs, so a learner that fails every
night keeps scoring on its old profile and nothing says so. This module is the pure part of the
answer, shared by `sa-learner` (the per-night events) and `service_api` (`/api/health`).

The freshness signal is `fitted_to`, the last DATE of data a profile used, which only a real fit
advances. It is deliberately not `computed_at`: `drift.apply_stability` re-stamps `computed_at` on
every profile whose stability it caps, so a learner whose fit failed would read as fresh for any
profile the drift detector touched. Only `presence_bridge` has no `fitted_to` (it fits whole-lake
bridges, not a dated window); it falls back to `computed_at`, which nothing else rewrites.

A healthy nightly fit at 03:30 UTC leaves `fitted_to` one day behind today (two just before the next
run), so `MAX_DAYS_BEHIND` = 2 flags a learner within about a day of its first missed night.
"""

from datetime import datetime, timezone

MAX_DAYS_BEHIND = 2
EVENT_SERVICE = "sa-learner"


def _as_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value


def days_behind(fitted_to, computed_at, today):
    """Whole days between `today` and the learner's data horizon, or None when it has neither
    stamp (a learner that has never fitted)."""
    horizon = _as_date(fitted_to) or _as_date(computed_at)
    if horizon is None:
        return None
    return (today - horizon).days


def stale_fits(rows, now, max_days_behind=MAX_DAYS_BEHIND):
    """The learners behind by more than `max_days_behind` days, worst first. `rows`: iterable of
    (learner, fitted_to, computed_at), one per learner (the newest stamps). A learner with no
    stamps at all is reported with `days_behind` None."""
    today = _as_date(now)
    stale = []
    for learner, fitted_to, computed_at in rows:
        behind = days_behind(fitted_to, computed_at, today)
        if behind is None or behind > max_days_behind:
            stale.append(
                {
                    "learner": learner,
                    "fitted_to": _as_date(fitted_to).isoformat() if fitted_to else None,
                    "days_behind": behind,
                }
            )
    return sorted(
        stale, key=lambda s: -(s["days_behind"] if s["days_behind"] is not None else 10**6)
    )


def summarize(rows, now, max_days_behind=MAX_DAYS_BEHIND):
    """The block `/api/health` reports: {"status", "checked_at", "learners", "stale"}."""
    rows = list(rows)
    stale = stale_fits(rows, now, max_days_behind)
    return {
        "status": "stale" if stale else "ok",
        "checked_at": now.isoformat() if hasattr(now, "isoformat") else str(now),
        "learners": len(rows),
        "max_days_behind": max_days_behind,
        "stale": stale,
    }


def fit_events(outcomes, now=None):
    """Event-stream events for one nightly run. `outcomes`: {learner: ("fit_ok", detail) |
    ("fit_failed", error text)}. One `fit_failed` warning per failure, and one `fit_ok` summary per
    run (not one per learner: the household event log should not gain nine rows a night)."""
    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%d%H%M%S")
    events = []
    failed = {name: detail for name, (verb, detail) in outcomes.items() if verb == "fit_failed"}
    for name, error in sorted(failed.items()):
        events.append(
            {
                "id": f"learner_fit_failed_{name}_{stamp}",
                "type": "warning",
                "message": f"Learner {name} failed to fit: {str(error)[:200]}",
                "time": now.isoformat(),
                "subject_type": "learner",
                "subject_id": name,
                "verb": "fit_failed",
                "service": EVENT_SERVICE,
            }
        )
    ok = sorted(name for name in outcomes if name not in failed)
    events.append(
        {
            "id": f"learner_fit_ok_{stamp}",
            "type": "info" if not failed else "warning",
            "message": f"{len(ok)} of {len(outcomes)} learners fitted"
            + (f"; failed: {', '.join(sorted(failed))}" if failed else ""),
            "time": now.isoformat(),
            "subject_type": "learner",
            "subject_id": "all",
            "verb": "fit_ok" if not failed else "fit_partial",
            "service": EVENT_SERVICE,
        }
    )
    return events
