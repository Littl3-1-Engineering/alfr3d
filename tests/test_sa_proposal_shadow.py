"""The shadow replay of layer-3 proposals (sa/proposal_shadow.py): what the proof predictor would
have proposed, labelled against what the household did, with the base rate beside it. It must
fit only on days before the one it judges, stay silent for an irregular lamp or one the executor
runs, and never be able to reach a device."""

import inspect
import random
from datetime import datetime, timedelta

from services.service_sa.sa import proposal_shadow, proposals

UTC = "UTC"
D0 = datetime(2026, 10, 1)


def _lamp(days, on_minutes=(5, 25), off=(23, 30), skip_last=False, seed=3):
    """A lamp that comes on a little after 17:00 and goes off at 23:30 every day."""
    rng = random.Random(seed)
    out = []
    for d in range(days):
        if skip_last and d == days - 1:
            continue  # the routine breaks on the last day: the lamp never comes on
        day = D0 + timedelta(days=d)
        out.append((day + timedelta(hours=17, minutes=rng.randint(*on_minutes)), "on"))
        out.append((day + timedelta(hours=off[0], minutes=off[1]), "off"))
    return out


def _replay(transitions, days_of_history, autonomy=(), days=7):
    end = D0 + timedelta(days=days_of_history)
    return proposal_shadow.replay_switch("switch.lamp", transitions, end, UTC, autonomy, days)


class TestShadowReplay:
    def test_a_regular_lamp_gets_proposals_that_the_household_acts_on(self):
        got = _replay(_lamp(30), 30)
        assert got["status"] == "replayed"
        evidence = got["evidence"]
        assert evidence["proposals"] >= 5 and evidence["acted_on"] == evidence["proposals"]
        assert evidence["acted_on_alfr3d"] == 0  # nothing here was done by Alfr3d
        assert all(p["action"] == "switch_on" for p in got["proposed"])

    def test_the_proposal_is_made_in_the_hour_before_the_lamp_comes_on(self):
        got = _replay(_lamp(30), 30)
        hours = {datetime.fromisoformat(p["at"]).hour for p in got["proposed"]}
        assert hours == {
            17
        }  # off at 17:00, 'usually on' by then: propose, and it comes on at 17:05+

    def test_the_base_rate_is_reported_beside_it(self):
        got = _replay(_lamp(30), 30)
        base = got["baseline"]["switch_on"]
        assert base["hours"] > 0 and 0 <= base["rate"] <= 1
        assert base["happened_anyway"] < base["hours"]  # most off-hours see no change

    def test_an_irregular_lamp_gets_no_proposals(self):
        rng = random.Random(9)
        tr, state = [], "off"
        for h in range(30 * 24):
            if rng.random() < 0.3:
                state = "on" if state == "off" else "off"
                tr.append((D0 + timedelta(hours=h, minutes=rng.randint(0, 59)), state))
        got = _replay(tr, 30)
        assert got["status"] == "no_proposals" and got["evidence"]["proposals"] == 0

    def test_too_little_history_is_silent(self):
        got = _replay(_lamp(6), 6)
        assert got["status"] == "no_proposals"
        assert got["recommendation"]["recommend"] is False

    def test_it_judges_a_day_only_from_the_days_before_it(self):
        # the lamp never comes on during the last day: a proposal for that day (made from the
        # earlier days) must be labelled ignored, not spared by looking at the day itself
        got = _replay(_lamp(30, skip_last=True), 30)
        last = [
            p
            for p in got["proposed"]
            if p["at"].startswith((D0 + timedelta(days=29)).date().isoformat())
        ]
        assert last and all(p["label"] == "ignored" for p in last)
        assert got["evidence"]["ignored"] >= 1

    def test_a_lamp_the_executor_runs_does_not_produce_proposals(self):
        tr = _lamp(30)
        own = [(t - timedelta(seconds=2), s) for t, s in tr]
        got = _replay(tr, 30, autonomy=own)
        assert got["status"] == "no_proposals"

    def test_a_proposal_whose_outcome_is_not_knowable_yet_is_not_counted(self):
        tr = _lamp(30)
        end = D0 + timedelta(days=29, hours=17, minutes=30)  # the last evening is still under way
        got = proposal_shadow.replay_switch("switch.lamp", tr, end, UTC, (), 7)
        last_day = (D0 + timedelta(days=29)).date().isoformat()
        assert not [
            p for p in got["proposed"] if p["at"].startswith(last_day) and p["label"] == "pending"
        ]

    def test_the_recommendation_is_the_real_one_from_the_contract(self):
        got = _replay(_lamp(30), 30)
        assert got["recommendation"] == proposals.recommend(got["evidence"])


class TestHelpers:
    def test_state_at_reads_the_last_event_at_or_before_a_moment(self):
        ev = [(D0 + timedelta(hours=1), "on"), (D0 + timedelta(hours=3), "off")]
        assert proposal_shadow.state_at(ev, D0) is None
        assert proposal_shadow.state_at(ev, D0 + timedelta(hours=1)) == "on"
        assert proposal_shadow.state_at(ev, D0 + timedelta(hours=2)) == "on"
        assert proposal_shadow.state_at(ev, D0 + timedelta(hours=5)) == "off"

    def test_an_empty_lake_is_an_empty_report(self, tmp_path):
        got = proposal_shadow.replay_lake(str(tmp_path))
        assert got["switches"] == [] and got["total"]["proposals"] == 0


class TestItCannotAct:
    def test_the_module_cannot_reach_a_device_or_a_network(self):
        source = inspect.getsource(proposal_shadow)
        for forbidden in (
            "device_control",
            "control_iot_device",
            "ha_control_device",
            "get_producer",
            "requests",
            "pymysql",
            "subprocess",
            "def execute",
        ):
            assert forbidden not in source
