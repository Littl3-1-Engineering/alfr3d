"""Calendar and gathering cards: events, travel, focus, gatherings, guest overstay, party.

Step 4d of the engine.py split (todo/sa/todo_parallel_capture_track.md, item 4): the constants and
the seven methods moved verbatim out of engine.py as `CalendarCards`, which `SAEngine` inherits;
engine re-exports the constants. `PARTY_ADVISORY_LAST_NUDGE_TIME` is module state mutated by
`check_party_advisory` (`global`), so it now lives, and is changed, here only.

`get_producer` is looked up in THIS module (check_gatherings, check_party_advisory), so tests
patch `sa.calendar_cards.get_producer` (the `sa.` import path engine uses, not
`services.service_sa.sa.`). The rest (`pymysql`, `routing_utils.*`, `spotify_utils.*`, `time`,
`focus_utils`) are shared module objects patched by attribute and are unaffected by the move.
"""

import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import orjson
import pymysql
from sa import focus_utils, routing_utils

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../common"))
from common import get_producer, spotify_utils  # noqa: E402

logger = logging.getLogger("SALog")

MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE")
MYSQL_DB = os.environ.get("MYSQL_NAME")
MYSQL_USER = os.environ.get("MYSQL_USER")
MYSQL_PSWD = os.environ.get("MYSQL_PSWD")
ENV_NAME = os.environ.get("ALFR3D_ENV_NAME")

# How far ahead of a call-like event's start time check_focus_needed() will fire.
FOCUS_LEAD_MINUTES = 15

# Spotify's own 0.0-1.0 "energy" audio feature above which check_party_advisory()
# considers what's actually playing to be genuinely high-energy, independent
# of ALFR3D's own (capped, on weeknights) recommendation.
PARTY_ADVISORY_ENERGY_THRESHOLD = 0.75

# Minimum time between check_party_advisory() spoken nudges, so a rowdy
# weeknight track doesn't get "it's a school night" repeated every polling
# cycle -- the card itself still refreshes every cycle, only the TTS nudge
# is rate-limited.
PARTY_ADVISORY_COOLDOWN_MINUTES = 60

# Last time check_party_advisory() spoke a nudge; 0.0 so the very first
# detection always speaks rather than waiting out a cooldown against an
# undefined "last time".
PARTY_ADVISORY_LAST_NUDGE_TIME = 0.0

# Continuous-stay guest decay: max how far check_gatherings() can nudge its own priority-3 slot
# as its guests' decayed energy (spotify_utils.aggregate_guest_energy()) drops toward
# spotify_utils.GUEST_STAY_ENERGY_FLOOR. 0.08 leaves a 0.02 cushion below now_playing's 3.1, so
# a fully-decayed guest population never crosses into the next rule's priority band.
GUEST_CARD_PRIORITY_MAX_DEMOTION = 0.08

# check_travel() (SA-6): once the computed leave-by time is more than this many minutes in the
# past, stop publishing the card -- a stale leave-by time is worse than no card. Deliberately
# one-sided: this used to also cap how far *ahead* of leave-by the card could appear (a symmetric
# +/- window), which meant a distant event's leave-by simply didn't exist on the wire yet no
# matter how much advance notice a consumer wanted. self-hosted OSRM has no live-traffic layer
# (see check_travel()'s own doc comment), so the drive-time estimate doesn't get more accurate by
# waiting -- there's no reason to withhold it. How far in advance to actually *show* the card is
# alfr3d_deck's call (EventLeaveByLifecycle.LEAD_TIME_MINUTES), not this service's.
TRAVEL_STALE_AFTER_MINUTES = 30


class CalendarCards:
    def check_events(self, frame):
        """Check for upcoming events, showing plain title/time info.

        `frame.upcoming_events` (SA-4) replaces this rule's own
        calendar_utils.get_upcoming_events() call -- check_focus_needed() reads the exact same
        query, so both now share the one fetch build_context_frame() makes per cycle.
        """
        events = frame.upcoming_events
        if not events:
            return None
        event = events[0]  # Take first
        if event["start_time"] - frame.now > timedelta(hours=3):
            return None  # Only care about events within next hour
        title = event["title"]
        start_time = event["start_time"]
        minutes_until = int((start_time - frame.now).total_seconds() / 60)
        content = f"Upcoming event: {title} at {frame.to_local(start_time).strftime('%I:%M %p')}"
        return {
            "mode": "event",
            "content": content,
            "priority": 2,
            "data": {
                "title": title,
                "start_time": start_time.isoformat(),
                "minutes_until": minutes_until,
                "because": [f"{title} starts in {minutes_until} min"],
            },
        }

    def check_travel(self, frame):
        """SA-6: restores what commit 08509ce removed (Google Maps Directions-based
        check_travel()), on self-hosted infrastructure -- see
        todo/sa/todo_self_hosted_routing.md for the Phase 0 spike that justified self-hosted OSRM
        for routing (measured live against real production hardware) plus the public Nominatim
        API for the much rarer geocoding need, over any paid/hosted alternative.

        Fires for any upcoming event (see UPCOMING_EVENTS_LOOKAHEAD_HOURS) that has a resolvable
        physical destination -- a non-empty `address` and no `conference_uri` (a video call has
        nowhere to drive to; that case is check_focus_needed()'s job, not this one's) -- as long
        as its computed leave-by time hasn't meaningfully passed yet (TRAVEL_STALE_AFTER_MINUTES).
        No upper bound on how far in advance: how soon to actually surface this to the household
        is a display decision, made downstream (see TRAVEL_STALE_AFTER_MINUTES's own doc comment).

        Fails closed and silent at every step: an ungeocodable address, a household location
        that hasn't been geocoded yet, or an unreachable routing container all mean no card,
        never a fabricated estimate -- the exact anti-pattern the original implementation was
        criticized for. `data.traffic_aware` is always `false`: none of the self-hosted routing
        engines evaluated match Google's live-traffic layer, so no consumer should present this
        as anything but a free-flow/typical-conditions estimate.
        """
        events = frame.upcoming_events
        if not events:
            return None
        event = events[0]
        address = (event.get("address") or "").strip()
        if not address or event.get("conference_uri"):
            return None
        start_time = event.get("start_time")
        if start_time is None or frame.now is None:
            return None

        dest = routing_utils.geocode_address(address)
        if dest is None:
            return None
        origin = routing_utils.fetch_home_coordinates(ENV_NAME)
        if origin is None:
            return None
        route = routing_utils.get_route(origin, dest)
        if route is None:
            return None

        leave_by = start_time - timedelta(minutes=route["duration_minutes"])
        minutes_until_leave = (leave_by - frame.now).total_seconds() / 60
        if minutes_until_leave < -TRAVEL_STALE_AFTER_MINUTES:
            return None

        title = event["title"]
        duration_minutes = round(route["duration_minutes"])
        distance_km = round(route["distance_km"], 1)
        content = f"Leave by {frame.to_local(leave_by).strftime('%I:%M %p')} for {title}"
        return {
            "mode": "travel",
            "content": content,
            "priority": 2.5,
            "data": {
                "duration_minutes": duration_minutes,
                "distance_km": distance_km,
                "traffic_aware": False,
                "leave_by": leave_by.isoformat(),
                "because": [f"{duration_minutes} min drive to {title}"],
            },
        }

    def check_focus_needed(self, frame):
        """Check whether the next upcoming event looks like a call starting soon.

        Reuses `frame.upcoming_events` (SA-4; same source check_events() reads) and applies
        focus_utils.looks_like_call() (SA-7) -- tiered by confidence: `focus_utils.CONFIRMED`
        when the event carries real synced conferencing data (`conference_uri`),
        `focus_utils.PROBABLE` when only the text heuristic over address/notes matches. See
        focus_utils' module docstring for the full tier breakdown and known false-positive
        shape of the probable tier. Only fires within FOCUS_LEAD_MINUTES of the event's start.

        DND correlation (todo/sa/todo_context_exchange_protocol.md Phase 2, and the deferred
        follow-up todo_attention_telemetry.md asked for): when a Deck reports Do Not Disturb
        already on, "Find a quiet spot." is advice the user has visibly already taken, so the
        card drops it and says so instead. It deliberately still *fires* -- the useful part of
        this card is "your call starts in N minutes," and silencing that because the phone is
        silenced would throw away the alert to preserve the footnote.

        Note the tri-state: only an explicit `True` changes the wording. A household with no
        Deck reporting (None) gets exactly the pre-Phase-2 card, rather than being treated as
        "DND off" and told something subtly wrong about a device nobody asked about.
        """
        events = frame.upcoming_events
        if not events:
            return None
        event = events[0]
        confidence = focus_utils.looks_like_call(
            event["address"], event["notes"], event.get("conference_uri")
        )
        if not confidence:
            return None
        start_time = event["start_time"]
        if start_time - frame.now > timedelta(minutes=FOCUS_LEAD_MINUTES):
            return None
        title = event["title"]
        start_label = frame.to_local(start_time).strftime("%I:%M %p")
        if confidence == focus_utils.CONFIRMED:
            solution = event.get("conference_solution") or "Call"
            lead = f"{solution} starting soon"
        else:
            lead = "Looks like a call starting soon"
        device_contexts = (frame.launcher_context and frame.launcher_context.device_contexts) or {}
        in_dnd = self._any_device_in_dnd(device_contexts)
        advice = "Do Not Disturb is already on." if in_dnd else "Find a quiet spot."
        content = f"{lead}: {title} at {start_label}. {advice}"
        minutes_until = int((start_time - frame.now).total_seconds() / 60)
        because = [
            f"{title} starts in {minutes_until} min",
            (
                "confirmed conferencing data"
                if confidence == focus_utils.CONFIRMED
                else "text looks like a call"
            ),
        ]
        if in_dnd:
            because.append("a Deck reports Do Not Disturb on")
        return {
            "mode": "focus_needed",
            "content": content,
            "priority": 3.5,
            "confidence": confidence,
            "conference_uri": event.get("conference_uri"),
            "dnd_active": in_dnd,
            "data": {
                "title": title,
                "start_time": start_time.isoformat(),
                "minutes_until": minutes_until,
                "because": because,
            },
        }

    def _online_guest_stay_days(self, cursor, now):
        """Continuous-stay guest decay: days-of-continuous-stay for every currently-online
        guest, shared by check_gatherings() (energy/priority) and
        check_guest_overstay_advisory() (the resolve-this nudge) so both read the same
        underlying signal. NULL continuous_stay_since (not yet backfilled, or a stay that
        hasn't started per service_user.app.update_user_state()) is treated as a fresh
        arrival (0 days) rather than fabricating an overstay from missing data.
        """
        cursor.execute(
            """
            SELECT username, continuous_stay_since
            FROM user u
            JOIN states s ON u.state = s.id
            JOIN user_types ut ON u.type = ut.id
            WHERE s.state = 'online' AND ut.type = 'guest' AND u.username != 'unknown'
            """
        )
        results = []
        for username, continuous_stay_since in cursor.fetchall():
            if continuous_stay_since:
                since = (
                    continuous_stay_since.replace(tzinfo=timezone.utc)
                    if continuous_stay_since.tzinfo is None
                    else continuous_stay_since
                )
                days = max(0.0, (now - since).total_seconds() / 86400)
            else:
                days = 0.0
            results.append((username, days))
        return results

    def check_gatherings(self, frame):
        """Check for gatherings (>3 guests/residents online).

        `frame.local_dt`/`frame.day_mood` (SA-4) replace this rule's own
        db_utils.get_env_local_time()/mood_utils.get_day_mood() calls -- check_party_advisory(),
        check_wind_down_signal(), and check_mood() all needed the exact same pair. `frame.
        environment`'s description/subjective_feel replace this rule's own separate read of the
        same `environment` row check_weather()/check_weather_advisory() also read.
        """
        db = None
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            cursor = db.cursor()
            cursor.execute(
                """
                SELECT
                    SUM(CASE WHEN ut.type IN ('guest') THEN 1 ELSE 0 END) as guest_count,
                    COUNT(*) as total_count
                FROM user u
                JOIN states s ON u.state = s.id
                JOIN user_types ut ON u.type = ut.id
                WHERE s.state = 'online' AND u.username != 'unknown'
                """
            )
            row = cursor.fetchone()
            # SUM() returns decimal.Decimal via pymysql (unlike COUNT()'s plain int) -- cast
            # so guest_count is safe to embed directly in the "data" dict's JSON payload (SA-5),
            # not just interpolated into f-string content like before.
            guest_count = int(row[0]) if row and row[0] else 0
            total_count = int(row[1]) if row and row[1] else 0

            if guest_count > 0:
                logger.info(
                    "Gathering detected with total people: "
                    + str(total_count)
                    + " (guests: "
                    + str(guest_count)
                    + ")"
                )
                if frame.local_dt is None or frame.day_mood is None:
                    return None
                local_dt = frame.local_dt
                time_of_day = frame.day_mood["time_of_day"]
                environment = frame.environment or {}
                weather_info = {
                    "description": environment.get("description"),
                    "subjective_feel": environment.get("subjective_feel"),
                }

                guest_stays = self._online_guest_stay_days(
                    cursor, frame.now or datetime.now(timezone.utc)
                )
                guest_energy_bonus = spotify_utils.aggregate_guest_energy(
                    [days for _, days in guest_stays]
                )

                reco = spotify_utils.recommend(
                    total_people=total_count,
                    guest_count=guest_count,
                    time_of_day=time_of_day,
                    weather=weather_info,
                    is_party_night=spotify_utils.is_party_night(local_dt),
                    guest_energy_bonus=guest_energy_bonus,
                )
                logger.info(f"Recommendation: {reco}")

                p = get_producer()
                if p:
                    event = {
                        "id": f"gathering_detected_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        "type": "info",
                        "message": (
                            f"Gathering detected with {total_count} people "
                            f"({guest_count} guests). Suggesting {reco['mood']} music "
                            f"({reco['genre']})."
                        ),
                        "time": datetime.now(timezone.utc).isoformat(),
                    }
                    p.send("event-stream", orjson.dumps(event))

                hint = reco.get("playlist_hint", reco.get("mood", ""))
                playlist = None
                try:
                    playlist = spotify_utils.resolve_playlist(hint, reco.get("genre", ""))
                except Exception as e:
                    logger.warning(f"Playlist resolution failed, using text hint only: {e}")

                display_name = playlist.get("name") if playlist else hint
                content = f"Play {display_name} ({reco['genre']}, energy={reco['energy']})"

                # Continuous-stay guest decay: demote this card's own priority as its guests'
                # decayed energy drops toward the floor -- a houseful of long-staying guests
                # shouldn't keep surfacing as prominently as a fresh gathering does.
                span = spotify_utils.GUEST_STAY_ENERGY_PEAK - spotify_utils.GUEST_STAY_ENERGY_FLOOR
                penalty = (
                    GUEST_CARD_PRIORITY_MAX_DEMOTION
                    * (spotify_utils.GUEST_STAY_ENERGY_PEAK - guest_energy_bonus)
                    / span
                )
                because = [f"{guest_count} guest(s) online", f"{time_of_day} time of day"]
                because.extend(
                    f"{username}: {days:.0f}d continuous, contribution "
                    f"{spotify_utils.guest_stay_energy_contribution(days):+.2f}"
                    for username, days in guest_stays
                )

                card = {
                    "mode": "music",
                    "content": content,
                    "priority": round(3.0 + penalty, 3),
                    "data": {
                        "mood": reco.get("mood"),
                        "genre": reco.get("genre"),
                        "energy": reco.get("energy"),
                        "tempo_hint": reco.get("tempo_hint"),
                        "guest_count": guest_count,
                        "total_count": total_count,
                        "time_of_day": time_of_day,
                        "guest_energy_contribution": round(guest_energy_bonus, 3),
                        "because": because,
                    },
                }
                if playlist:
                    card.update(
                        {
                            "playlist_id": playlist.get("id"),
                            "playlist_name": playlist.get("name"),
                            "playlist_uri": playlist.get("uri"),
                            "playlist_url": playlist.get("url"),
                            "playlist_image": playlist.get("image"),
                            "playlist_source": playlist.get("source"),
                        }
                    )
                return card
            return None
        except pymysql.Error as e:
            logger.error("Gathering check error: " + str(e))
            if db:
                db.rollback()
            return None
        finally:
            if db:
                db.close()

    def check_guest_overstay_advisory(self, frame):
        """Continuous-stay guest decay: once a guest's decayed energy contribution
        (spotify_utils.guest_stay_energy_contribution(), see check_gatherings()/
        _online_guest_stay_days()) has gone negative -- day ~14+ of an unbroken stay -- nudge
        the household to actually resolve the situation before their continued presence drags
        the household energy down further: promote them to resident, or address the overstay.

        Only one card per cycle, same "single most-overdue" precedent as
        check_departure_anomaly()/check_rhythm_break_anomaly() -- picks the guest whose
        contribution has decayed furthest negative. CARD_SUPPRESSION_COOLDOWN_MINUTES_BY_RULE
        keeps this from re-firing more than once a day, since the underlying signal (days of
        stay) only moves that slowly.
        """
        db = None
        try:
            db = pymysql.connect(
                host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB
            )
            cursor = db.cursor()
            guest_stays = self._online_guest_stay_days(
                cursor, frame.now or datetime.now(timezone.utc)
            )
            overstaying = [
                (spotify_utils.guest_stay_energy_contribution(days), username, days)
                for username, days in guest_stays
            ]
            overstaying = [row for row in overstaying if row[0] < 0]
            if not overstaying:
                return None

            overstaying.sort()
            contribution, username, days = overstaying[0]
            return {
                "mode": "guest_overstay_advisory",
                "content": (
                    f"{username} has been staying continuously for {int(days)} day(s) — "
                    "consider promoting them to resident, or addressing the overstay"
                ),
                "priority": 3.15,
                "entity_name": username,
                "data": {
                    "days_continuous": round(days, 1),
                    "energy_contribution": round(contribution, 3),
                    "because": [
                        f"{int(days)} days of continuous stay",
                        f"energy contribution {contribution:+.2f} (negative past day 14)",
                    ],
                },
            }
        except pymysql.Error as e:
            logger.error("Guest overstay advisory check error: " + str(e))
            if db:
                db.rollback()
            return None
        finally:
            if db:
                db.close()

    def check_party_advisory(self, frame):
        """Catch a real, high-energy gathering happening despite the capped
        weeknight recommendation -- e.g. someone manually queues something
        rowdy on a Tuesday -- and nudge toward winding down.

        `common.spotify_utils.recommend()` only ever *suggests* capped
        energy on non-party nights (see its `is_party_night` param); nothing
        stops residents/guests from playing something high-energy anyway.
        This checks what's actually playing via Spotify's own 0.0-1.0
        'energy' audio feature for the current track, independent of
        ALFR3D's own estimate. Only evaluated outside the household's
        declared Friday/Saturday party-night window and once it's genuinely
        late (time_of_day == "night"), not just any weeknight evening.

        The returned card refreshes every cycle like any other display, but
        the spoken nudge over the `speak` topic is cooldown-gated
        (PARTY_ADVISORY_COOLDOWN_MINUTES) so it doesn't repeat the same
        "school night" line every polling cycle.

        `frame.local_dt`/`frame.day_mood`/`frame.playback` (SA-4) replace this rule's own
        get_env_local_time()/get_day_mood()/get_playback_state() calls --
        check_gatherings()/check_wind_down_signal()/check_mood() share the first two,
        check_now_playing() shares the third. get_track_energy() below stays its own call --
        a different Spotify endpoint (audio features, not playback state) that depends on
        the track id this same fetch already resolved, so there's nothing to share it with.
        """
        global PARTY_ADVISORY_LAST_NUDGE_TIME
        try:
            if frame.local_dt is None or frame.day_mood is None:
                return None
            local_dt = frame.local_dt
            if spotify_utils.is_party_night(local_dt):
                return None

            day_mood = frame.day_mood
            if day_mood["time_of_day"] != "night":
                return None

            from common import spotify_utils as spotify_api

            state = frame.playback or {}
            item = state.get("item") or {}
            track_id = item.get("id")
            if not state.get("is_playing") or not track_id:
                return None

            energy = spotify_api.get_track_energy(track_id)
            if energy is None or energy < PARTY_ADVISORY_ENERGY_THRESHOLD:
                return None

            track_name = item.get("name") or "the music"
            content = (
                f'"{track_name}" is still high-energy for a {day_mood["day_of_week"]} '
                "night -- work tomorrow, might be worth winding down."
            )

            if time.time() - PARTY_ADVISORY_LAST_NUDGE_TIME > PARTY_ADVISORY_COOLDOWN_MINUTES * 60:
                p = get_producer()
                if p:
                    p.send(
                        "speak",
                        (
                            f'Hey, it\'s a {day_mood["day_of_week"]} night and the music is '
                            "still pretty high energy. Just a heads up, it's a work night."
                        ).encode("utf-8"),
                    )
                PARTY_ADVISORY_LAST_NUDGE_TIME = time.time()

            return {
                "mode": "party_advisory",
                "content": content,
                "priority": 3.2,
                "data": {
                    "track_name": track_name,
                    "energy": energy,
                    "day_of_week": day_mood["day_of_week"],
                    "because": [
                        f"track energy {energy:.2f} >= {PARTY_ADVISORY_ENERGY_THRESHOLD}",
                        f"{day_mood['day_of_week']} night",
                    ],
                },
            }
        except Exception as e:
            logger.error("Party advisory check error: " + str(e))
            return None
