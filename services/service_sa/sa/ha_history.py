"""Home Assistant state history -> Parquet bronze (LF-0b, todo/sa/todo_signal_inventory.md).

Home Assistant knows about IoT device states, the OpenWeatherMap conditions and forecast, phone
battery and charger state, network speed tests, media players, the sun, who is home. ALFR3D only
ever kept the *current* value of those (smarthome_devices.last_state). Home Assistant's own recorder
keeps about **10 days** and then purges, so before this module the history was being lost at a day
per day, with no way to get it back.

This module copies every entity's state changes into the lake:

    <lake>/bronze/ha_state_history/date=YYYY-MM-DD/part-0.parquet
    columns: entity_id, domain, state, last_changed, last_updated   (naive UTC)

State changes only, on-change timestamps (more precise than the 15-minute sync could give), all
entities: the whole of Home Assistant produced ~650 points a day when probed, so there is nothing to
gain by filtering and a lot to lose by guessing what a future learner will want.

Left out, on purpose:
- **Attributes.** They carry signed entity-picture tokens, and the useful values are already their
  own entities (temperature, humidity, pressure, battery are all separate sensors).
- **Pushbullet.** Legacy: Pushbullet (like ntfy.sh) is how ALFR3D delivered notifications before
  Kafka and the backend event stream existed, and neither is used any more. The `pushbullet`
  entities Home Assistant still exposes are leftovers, and their state is notification text, so the
  whole family is excluded, not just the body. Exclusions are applied **retroactively** (see
  `purge_excluded`): changing one removes what was already stored, on the next run.

Home Assistant 2023.8 requires an explicit entity list on history requests, so each run lists the
current entities from /api/states and fetches them in chunks. An entity that has since been removed
from Home Assistant is therefore not re-fetched, but what was already exported stays.

Incremental like the MySQL exports: resume from the newest partition, with a lookback, merging by
(entity_id, last_changed). The first run has no partitions and walks backwards a day at a time until
it reaches the end of Home Assistant's retention (three empty days in a row).
"""

import json
import logging
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import requests

from sa import lake

logger = logging.getLogger("SAHaHistory")

TABLE = "ha_state_history"
CHUNK_ENTITIES = 30
REQUEST_TIMEOUT = 60
# The first run goes back at most this far (HA keeps ~10 days; this only bounds a misbehaving API).
MAX_BACKFILL_DAYS = 30
# Stop the backward walk after this many consecutive days with no data at all.
EMPTY_DAYS_TO_STOP = 3

# Entities never stored. Matched against the full entity id. Pushbullet is a legacy notification
# channel that ALFR3D no longer uses; its entities carry notification text.
EXCLUDED_ENTITIES = re.compile(r"pushbullet", re.IGNORECASE)

SCHEMA = pa.schema(
    [
        pa.field("entity_id", pa.string()),
        pa.field("domain", pa.string()),
        pa.field("state", pa.string()),
        pa.field("last_changed", pa.timestamp("us")),
        pa.field("last_updated", pa.timestamp("us")),
    ]
)
KEY = (0, 3)  # (entity_id, last_changed)


def _utc(iso):
    """HA's ISO timestamp (with offset) -> naive UTC datetime."""
    return datetime.fromisoformat(iso).astimezone(timezone.utc).replace(tzinfo=None)


def _iso(dt):
    return dt.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def list_entities(base_url, headers, get=requests.get):
    """Entity ids Home Assistant currently knows, minus the excluded ones."""
    response = get(f"{base_url}/api/states", headers=headers, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return sorted(
        s["entity_id"] for s in response.json() if not EXCLUDED_ENTITIES.search(s["entity_id"])
    )


def fetch_window(base_url, headers, entity_ids, start, end, get=requests.get):
    """State rows for every entity in [start, end] (naive UTC), fetched in chunks. Includes the
    state in effect at `start` (HA's default), which anchors an entity that doesn't change."""
    rows = []
    for i in range(0, len(entity_ids), CHUNK_ENTITIES):
        chunk = entity_ids[i : i + CHUNK_ENTITIES]
        response = get(
            f"{base_url}/api/history/period/{_iso(start)}",
            headers=headers,
            params={
                "filter_entity_id": ",".join(chunk),
                "end_time": _iso(end),
                "no_attributes": "",
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        for series in response.json():
            for point in series:
                entity_id = point["entity_id"]
                rows.append(
                    [
                        entity_id,
                        entity_id.split(".", 1)[0],
                        str(point["state"]),
                        _utc(point["last_changed"]),
                        _utc(point.get("last_updated") or point["last_changed"]),
                    ]
                )
    return rows


def purge_excluded(table_dir):
    """Remove rows for excluded entities from partitions already on disk, so tightening
    EXCLUDED_ENTITIES takes effect on data stored earlier. Returns how many rows were removed."""
    removed = 0
    for part in sorted(Path(table_dir).glob("date=*/part-0.parquet")):
        rows = pq.read_table(part).to_pylist()
        kept = [r for r in rows if not EXCLUDED_ENTITIES.search(r["entity_id"])]
        if len(kept) == len(rows):
            continue
        removed += len(rows) - len(kept)
        label = part.parent.name.split("=", 1)[1]
        if kept:
            lake._write_partition(
                Path(table_dir), label, SCHEMA, [[r[n] for n in SCHEMA.names] for r in kept]
            )
        else:
            shutil.rmtree(part.parent)
    return removed


CONFIG_FILE = "_ha_config.json"


def fetch_config(base_url, headers, get=requests.get):
    """Home Assistant's configured home: the coordinates, timezone and name that its OpenWeatherMap
    weather, its sun entities and its home zone are all computed for."""
    response = get(f"{base_url}/api/config", headers=headers, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    body = response.json()
    return {
        "latitude": body.get("latitude"),
        "longitude": body.get("longitude"),
        "time_zone": body.get("time_zone"),
        "location_name": body.get("location_name"),
    }


def record_config(table_dir, config, now_utc):
    """Keep HA's home location in <table>/_ha_config.json: the current value plus a history that
    gains an entry only when it changes. Home Assistant's home was found to still be the old house
    in Novi Sad (2026-10-10) after the household moved to Etobicoke, so every HA weather and sun
    series describes the wrong place; when the location is corrected, this history is what lets
    silver tell the two regimes apart. Returns True if the location changed."""
    path = Path(table_dir) / CONFIG_FILE
    try:
        state = json.loads(path.read_text())
    except (OSError, ValueError):
        state = {"current": None, "history": []}
    if state.get("current") == config:
        return False
    state["current"] = config
    state["history"].append({"observed_at": now_utc.replace(microsecond=0).isoformat(), **config})
    path.write_text(json.dumps(state, indent=2))
    return True


def _merge_rows(table_dir, rows):
    """Group rows by the UTC day of last_changed and merge each day's partition. Returns days
    touched."""
    by_day = {}
    for row in rows:
        by_day.setdefault(row[3].date().isoformat(), []).append(row)
    for label, day_rows in by_day.items():
        lake.merge_partition(table_dir, label, SCHEMA, day_rows, KEY)
    return len(by_day)


def export_ha_history(lake_dir=None, now_utc=None, progress=None, get=requests.get, config=None):
    """Export Home Assistant history to bronze. Returns {"rows", "days", "entities"} or
    {"skipped": reason}. `config` and `get` are injectable for tests."""
    lake_dir = lake_dir or lake.LAKE_DIR
    if config is None:
        from common import ha_utils

        config = ha_utils.get_ha_config()
    base_url = (config.get("ha_url") or "").rstrip("/")
    token = config.get("ha_token") or ""
    if not base_url or not token:
        return {"skipped": "Home Assistant is not configured"}
    headers = {"Authorization": f"Bearer {token}"}

    now_utc = now_utc or datetime.now(timezone.utc).replace(tzinfo=None)
    table_dir = Path(lake_dir) / "bronze" / TABLE
    table_dir.mkdir(parents=True, exist_ok=True)
    for stale in table_dir.glob(".tmp-date=*"):
        shutil.rmtree(stale, ignore_errors=True)

    purged = purge_excluded(table_dir)
    if purged:
        logger.info(f"ha history: purged {purged} row(s) of excluded entities")
    entities = list_entities(base_url, headers, get)
    since = lake._resume_since(table_dir, now_utc.date())
    total_rows = total_days = 0

    if since is not None:
        rows = fetch_window(base_url, headers, entities, since, now_utc, get)
        total_rows, total_days = len(rows), _merge_rows(table_dir, rows)
        if progress:
            progress()
    else:
        # Backfill: one day at a time, newest first, until Home Assistant has nothing older.
        day = datetime.combine(now_utc.date(), datetime.min.time())
        end = now_utc
        empty_in_a_row = 0
        for _ in range(MAX_BACKFILL_DAYS):
            rows = fetch_window(base_url, headers, entities, day, end, get)
            if rows:
                empty_in_a_row = 0
                total_rows += len(rows)
                total_days += _merge_rows(table_dir, rows)
            else:
                empty_in_a_row += 1
                if empty_in_a_row >= EMPTY_DAYS_TO_STOP:
                    break
            if progress:
                progress()
            end, day = day, day - timedelta(days=1)

    try:
        if record_config(table_dir, fetch_config(base_url, headers, get), now_utc):
            logger.info("ha history: Home Assistant's configured home location changed (or is new)")
    except Exception as e:  # noqa: BLE001 -- the location note must never fail the export
        logger.warning(f"ha history: could not read Home Assistant's config: {e}")
    lake.write_horizon(table_dir, now_utc)
    logger.info(
        f"ha history: {total_rows} points over {total_days} day(s), {len(entities)} entities"
    )
    return {"rows": total_rows, "days": total_days, "entities": len(entities)}


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(asctime)s - %(message)s")
    with lake._ExportLock(lake.LAKE_DIR):
        print(export_ha_history())
