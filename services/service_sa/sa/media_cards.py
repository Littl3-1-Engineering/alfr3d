"""Media cards: now playing and cross-surface continuity.

Step 4c of the engine.py split (todo/sa/todo_parallel_capture_track.md, item 4): the constants,
`_write_now_playing_config` and the two `check_*` methods moved verbatim out of engine.py as
`MediaCards`, which `SAEngine` inherits; engine re-exports the constants (it still reads
NOW_PLAYING_CONFIG_KEY when it builds the context frame). `_read_config_json` stays on engine: the
frame builder uses it too. Everything called here is a shared module object (`pymysql`, `orjson`),
so existing tests are unaffected.
"""

import logging
import os
from datetime import datetime, timedelta, timezone

import orjson
import pymysql

logger = logging.getLogger("SALog")

MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE")
MYSQL_DB = os.environ.get("MYSQL_NAME")
MYSQL_USER = os.environ.get("MYSQL_USER")
MYSQL_PSWD = os.environ.get("MYSQL_PSWD")

# `config` table key check_now_playing() persists the last-seen track under,
# so the value survives daemon restarts and is queryable by other services.
NOW_PLAYING_CONFIG_KEY = "music_now_playing"

# check_cross_surface_continuity() only offers a resume for state reported/
# updated within this many minutes -- a paused track or edited routine from
# hours ago isn't "picking up where you left off" anymore.
CROSS_SURFACE_STALENESS_MINUTES = 45


class MediaCards:
    def _write_now_playing_config(self, state):
        """Upsert the now-playing state into `config`, following the same
        UPDATE-then-INSERT-if-0-rows pattern used elsewhere for this table
        (e.g. spotify_utils.save_spotify_credentials())."""
        db = None
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            cursor = db.cursor()
            value = orjson.dumps(state).decode("utf-8")
            cursor.execute(
                "UPDATE config SET value = %s WHERE name = %s",
                (value, NOW_PLAYING_CONFIG_KEY),
            )
            if cursor.rowcount == 0:
                cursor.execute(
                    "INSERT INTO config (name, value) VALUES (%s, %s)",
                    (NOW_PLAYING_CONFIG_KEY, value),
                )
            db.commit()
        except Exception as e:
            logger.error(f"Now playing config write error: {e}")
        finally:
            if db:
                db.close()

    def check_now_playing(self, frame):
        """Surface a situational-awareness card for whatever's actually
        playing on Spotify right now, independent of check_gatherings()'s
        recommendation card.

        Runs every ~60s cycle like every other DISPLAY_RULES check (no
        separate poll loop -- the daemon's outer loop only ticks that often
        anyway). Only persists to `config` when the track or play state
        actually changed. It publishes no event: the daemon's
        now_playing_monitor already announces every track change (with the
        track details the Nexus card uses), and a second `play_start` here put
        two lines per song in the event log and doubled every play_start count
        the rate and household-day learners read.

        Persists on a play->pause transition too (not just track changes),
        even though no card is returned for the paused state itself --
        check_cross_surface_continuity() needs that persisted "paused N
        minutes ago" state to offer a resume. Before that feature existed,
        pausing never got persisted at all here.

        `frame.playback` (SA-4) replaces this rule's own
        spotify_api.get_playback_state() call -- check_party_advisory() reads the exact same
        fetch. `frame.persisted_now_playing` replaces reading NOW_PLAYING_CONFIG_KEY here --
        check_cross_surface_continuity() reads that same config row too.
        """
        try:
            state = frame.playback or {}
            item = state.get("item") or {}
            track_id = item.get("id")
            is_playing = state.get("is_playing", False)
            if not track_id:
                return None

            # config.value is VARCHAR(512) -- cap title/artist defensively
            # (no album art is stored here; that's re-fetched live from
            # GET /api/music/spotify/status when needed).
            title = (item.get("name") or "")[:150]
            artist = ", ".join(item.get("artists") or [])[:150]

            last = frame.persisted_now_playing or {}
            if last.get("track_id") != track_id or last.get("is_playing") != is_playing:
                self._write_now_playing_config(
                    {
                        "track_id": track_id,
                        "title": title,
                        "artist": artist,
                        "is_playing": is_playing,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
            if not is_playing:
                return None

            content = f"{title} — {artist}" if artist else title
            return {
                "mode": "music",
                "content": f"Now playing: {content}",
                "priority": 3.1,
                "track_title": title,
                "track_artist": artist,
                "is_playing": is_playing,
            }
        except Exception as e:
            logger.error(f"Now playing check error: {e}")
            return None

    def check_cross_surface_continuity(self, frame):
        """Offer a "pick up where you left off" resume for whichever surface
        was most recently left active: paused Spotify playback, an edited
        Matrix routine, or a reported launcher (terminal) session. Reads
        three existing signals rather than tracking anything new -- see
        todo/sa/todo_cross_surface_continuity.md.

        Each candidate is discarded if older than
        CROSS_SURFACE_STALENESS_MINUTES -- a paused track from hours ago
        isn't "picking up where you left off" anymore. Returns whichever
        surviving candidate is most recent.

        `frame.persisted_now_playing`/`frame.launcher_context.surface_state` (SA-4) replace
        this rule's own NOW_PLAYING_CONFIG_KEY/SURFACE_STATE_CONFIG_KEY reads --
        check_now_playing() reads the same now-playing config row, and the surface-state row
        isn't duplicated elsewhere but moved into the frame for consistency. The routines
        query below isn't duplicated by anything else, so it stays its own query.
        """
        now = frame.now
        staleness = timedelta(minutes=CROSS_SURFACE_STALENESS_MINUTES)
        candidates = []

        now_playing = frame.persisted_now_playing or {}
        if now_playing.get("is_playing") is False and now_playing.get("updated_at"):
            try:
                paused_at = datetime.fromisoformat(now_playing["updated_at"])
            except ValueError:
                paused_at = None
            if paused_at and now - paused_at <= staleness:
                title = now_playing.get("title") or "your last track"
                minutes_ago = int((now - paused_at).total_seconds() / 60)
                candidates.append(
                    (
                        paused_at,
                        {
                            "mode": "cross_surface_continuity",
                            "content": f"{title} paused {minutes_ago} min ago — resume?",
                            "priority": 5.5,
                            "resume_type": "music",
                            "resume_target": now_playing.get("track_id"),
                            "data": {"minutes_ago": minutes_ago},
                        },
                    )
                )

        surface_state = (frame.launcher_context and frame.launcher_context.surface_state) or {}
        if surface_state.get("terminal_session_active") and surface_state.get("updated_at"):
            try:
                reported_at = datetime.fromisoformat(surface_state["updated_at"])
            except ValueError:
                reported_at = None
            if reported_at and now - reported_at <= staleness:
                candidates.append(
                    (
                        reported_at,
                        {
                            "mode": "cross_surface_continuity",
                            "content": "Terminal session still open — resume on the Deck?",
                            "priority": 5.5,
                            "resume_type": "terminal",
                            "resume_target": None,
                        },
                    )
                )

        db = None
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            cursor = db.cursor()
            cursor.execute(
                "SELECT name, updated_at FROM routines WHERE updated_at IS NOT NULL "
                "ORDER BY updated_at DESC LIMIT 1"
            )
            row = cursor.fetchone()
            if row:
                name, updated_at = row
                edited_at = updated_at.replace(tzinfo=timezone.utc)
                if now - edited_at <= staleness:
                    candidates.append(
                        (
                            edited_at,
                            {
                                "mode": "cross_surface_continuity",
                                "content": f'"{name}" routine edited recently — reopen it?',
                                "priority": 5.5,
                                "resume_type": "routine",
                                "resume_target": name,
                            },
                        )
                    )
        except pymysql.Error as e:
            logger.error("Cross-surface continuity routine check error: " + str(e))
        finally:
            if db:
                db.close()

        if not candidates:
            return None
        candidates.sort(key=lambda c: c[0], reverse=True)
        return candidates[0][1]
