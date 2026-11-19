"""Capture ledger (Timeline "Context learning 2/5").

For every registered context feature and every series in `scalar_hourly`: whether it is captured,
since when, how much of the last window it actually covers, how long its source keeps it, who reads
it, and where it comes from. Read-only: it opens the Parquet lake and the registry, nothing else.

    python -m sa.ledger [--window-days 30] [--lake DIR]

It answers "what do we actually have to learn from" from the data, not from a document, which is
the point: captured history, not modelling, is the binding constraint. A series whose prefix is not
registered is listed under `unregistered`, so a new source cannot slip into the lake unseen.
"""

import json
import os
from datetime import timedelta

from sa import context_registry as reg


def _status(feature):
    if feature.privacy == reg.RESTRICTED:
        return "restricted"
    if feature.value is None:
        return "not_captured"
    return "captured"


def _entry(kind, key, meta, stats, horizon, window_days):
    hours_window = stats["hours_window"] if stats else 0
    return {
        "kind": kind,
        "key": key,
        "status": meta["status"],
        "capture_start": stats["first"].isoformat() if stats else None,
        "last_seen": stats["last"].isoformat() if stats else None,
        "rows": stats["rows"] if stats else 0,
        f"hours_with_data_{window_days}d": hours_window,
        f"coverage_{window_days}d": round(hours_window / (window_days * 24.0), 3) if stats else 0.0,
        "retention_days": meta["retention_days"],
        "privacy": meta["privacy"],
        "readers": list(meta["readers"]),
        "provenance": meta["provenance"],
        "note": meta.get("note", ""),
    }


def build(lake_dir, window_days=30, features=reg.REGISTRY, families=reg.SERIES_FAMILIES):
    """The ledger as a dict: {"horizon", "window_days", "features": [...], "series": [...],
    "unregistered": [...]}."""
    import duckdb

    def path(table):
        p = os.path.join(lake_dir, "gold", table, "part-0.parquet")
        return p if os.path.exists(p) else None

    con = duckdb.connect()
    try:
        f_path, s_path = path("context_features"), path("scalar_hourly")
        horizons = []
        for p, col in ((f_path, "bucket_utc"), (s_path, "bucket_utc")):
            if p:
                horizons.append(
                    con.execute(f"SELECT MAX({col}) FROM read_parquet('{p}')").fetchone()[0]
                )
        horizon = max((h for h in horizons if h is not None), default=None)
        since = horizon - timedelta(days=window_days) if horizon else None

        feature_stats = {}
        if f_path and horizon:
            for key, first, last, rows, recent in con.execute(
                f"SELECT feature_key, MIN(bucket_utc), MAX(bucket_utc), COUNT(*), "
                f"COUNT(DISTINCT bucket_utc) FILTER (WHERE bucket_utc > ?) "
                f"FROM read_parquet('{f_path}') GROUP BY feature_key",
                [since],
            ).fetchall():
                feature_stats[key] = {
                    "first": first,
                    "last": last,
                    "rows": rows,
                    "hours_window": recent,
                }

        series_stats = {}
        if s_path and horizon:
            for key, first, last, rows, recent in con.execute(
                f"SELECT series_key, MIN(bucket_utc), MAX(bucket_utc), COUNT(*), "
                f"COUNT(DISTINCT bucket_utc) FILTER (WHERE bucket_utc > ?) "
                f"FROM read_parquet('{s_path}') GROUP BY series_key ORDER BY series_key",
                [since],
            ).fetchall():
                series_stats[key] = {
                    "first": first,
                    "last": last,
                    "rows": rows,
                    "hours_window": recent,
                }
    finally:
        con.close()

    out_features = []
    for f in features:
        meta = {
            "status": _status(f),
            "retention_days": f.retention_days,
            "privacy": f.privacy,
            "readers": f.readers,
            "provenance": f.provenance,
            "note": f.description,
        }
        out_features.append(
            _entry("feature", f.key, meta, feature_stats.get(f.key), horizon, window_days)
        )

    out_series, unregistered = [], []
    for key, stats in sorted(series_stats.items()):
        family = next((fam for fam in families if key.startswith(fam.prefix)), None)
        if family is None:
            unregistered.append(key)
            continue
        meta = {
            "status": "captured" if family.privacy != reg.RESTRICTED else "restricted",
            "retention_days": family.retention_days,
            "privacy": family.privacy,
            "readers": family.readers,
            "provenance": family.provenance,
        }
        entry = _entry("series", key, meta, stats, horizon, window_days)
        entry["identity"] = family.identity
        out_series.append(entry)

    return {
        "horizon": horizon.isoformat() if horizon else None,
        "window_days": window_days,
        "features": out_features,
        "series": out_series,
        "unregistered": unregistered,
    }


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description="Context capture ledger (read-only)")
    parser.add_argument("--lake", default=os.environ.get("SA_LAKE_DIR", "/lake"))
    parser.add_argument("--window-days", type=int, default=30)
    args = parser.parse_args(argv)
    ledger = build(args.lake, args.window_days)
    print(json.dumps(ledger, indent=2))
    return ledger


if __name__ == "__main__":
    main()
