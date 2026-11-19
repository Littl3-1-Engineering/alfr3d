"""Safety net for splitting `sa/engine.py` (todo/sa/todo_parallel_capture_track.md, item 4).

The split is meant to be a PURE MOVE: methods and helpers change module, nothing else. This file
makes that checkable. It pins four things against a snapshot taken before any code moved:

1. every method of `SAEngine` (name, signature and a hash of its source), so after the split each
   one must still resolve on the class AND be byte-identical, which flags an edit hiding inside a
   move (a unit test only notices if it happens to cover the line);
2. every module-level function and constant of `engine` (the same, by hash);
3. `DISPLAY_RULES` (rule id, priority, check method) and the card budget `MAX_DISPLAYS == 26`;
4. the names tests patch on the `engine` module (`engine.get_producer`, `engine.pymysql`, ...):
   a patch replaces a name in `engine`'s own namespace, so code that moves must keep reading those
   names through `engine`, and the names must keep existing there.

Regenerate the snapshot only on purpose, in a commit that says why:

    UPDATE_ENGINE_SNAPSHOT=1 pytest tests/test_sa_engine_structure.py
"""

import hashlib
import inspect
import json
import os
import textwrap
from pathlib import Path

import pytest

from services.service_sa.sa import engine

SNAPSHOT = Path(__file__).parent / "data" / "sa_engine_surface.json"

# Names the existing tests reach through the `engine` module (found by grep over tests/*.py:
# `patch("...engine.NAME")` and `engine.NAME`). They must stay resolvable there.
PATCHED_NAMES = (
    "CARD_SUBJECT_KEY_EXTRACTORS",
    "DISK_HEALTH_STATE",
    "SYSTEM_HEALTH_STATE",
    "SAEngine",
    "calendar_utils",
    "context_frame",
    "db_utils",
    "disk",
    "get_producer",
    "gmail_utils",
    "inference_store",
    "pymysql",
    "routing_utils",
    "spotify_utils",
    "time",
)


def _digest(obj):
    source = textwrap.dedent(inspect.getsource(obj)).rstrip()
    # prefixed so the snapshot's values are not bare hex strings: detect-secrets reads those as keys
    return "sha256:" + hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def current_surface():
    methods = {}
    for name, fn in inspect.getmembers(engine.SAEngine, inspect.isfunction):
        methods[name] = {"signature": str(inspect.signature(fn)), "sha": _digest(fn)}
    functions = {
        name: {"signature": str(inspect.signature(fn)), "sha": _digest(fn)}
        for name, fn in inspect.getmembers(engine, inspect.isfunction)
        if fn.__module__ == engine.__name__
    }
    return {
        "methods": methods,
        "module_functions": functions,
        "display_rules": [list(rule) for rule in engine.SAEngine.DISPLAY_RULES],
        "max_displays": engine.SAEngine.MAX_DISPLAYS,
    }


if os.environ.get("UPDATE_ENGINE_SNAPSHOT"):
    SNAPSHOT.write_text(json.dumps(current_surface(), indent=1, sort_keys=True) + "\n")


@pytest.fixture(scope="module")
def snapshot():
    return json.loads(SNAPSHOT.read_text())


class TestTheSplitIsAPureMove:
    def test_every_method_still_exists_with_the_same_signature_and_source(self, snapshot):
        now = current_surface()["methods"]

        missing = sorted(set(snapshot["methods"]) - set(now))
        assert missing == [], f"methods no longer on SAEngine: {missing}"
        changed = sorted(
            name
            for name, was in snapshot["methods"].items()
            if now[name]["signature"] != was["signature"] or now[name]["sha"] != was["sha"]
        )
        assert changed == [], f"methods edited (not just moved): {changed}"

    def test_no_method_appeared_unreviewed(self, snapshot):
        now = current_surface()["methods"]

        extra = sorted(set(now) - set(snapshot["methods"]))
        assert extra == [], f"new SAEngine methods (regenerate the snapshot on purpose): {extra}"

    def test_module_level_helpers_keep_their_source(self, snapshot):
        # A helper may MOVE out of engine (and be re-exported); it may not be edited in place.
        for name, was in snapshot["module_functions"].items():
            fn = getattr(engine, name, None)
            assert fn is not None, f"engine no longer exposes {name}"
            assert _digest(fn) == was["sha"], f"{name} was edited, not just moved"

    def test_the_display_rules_and_the_card_budget_are_unchanged(self, snapshot):
        surface = current_surface()

        assert surface["display_rules"] == snapshot["display_rules"]
        assert surface["max_displays"] == snapshot["max_displays"] == 26
        assert len(engine.SAEngine.DISPLAY_RULES) == 26

    def test_every_display_rule_names_a_real_method(self):
        for _rule_id, _priority, check_name in engine.SAEngine.DISPLAY_RULES:
            assert callable(getattr(engine.SAEngine, check_name)), check_name


class TestThePatchContract:
    @pytest.mark.parametrize("name", PATCHED_NAMES)
    def test_the_name_tests_patch_still_lives_in_the_engine_namespace(self, name):
        assert hasattr(engine, name), f"engine.{name} is patched by tests and must stay there"

    def test_get_producer_is_a_name_in_engine_not_a_reference_to_another_module(self):
        # patch("...engine.get_producer") only works while engine itself calls it by that name.
        assert "get_producer" in vars(engine)

    def test_methods_resolve_through_the_class_whatever_module_they_live_in(self):
        engine_obj = engine.SAEngine.__new__(engine.SAEngine)

        for _rule_id, _priority, check_name in engine.SAEngine.DISPLAY_RULES:
            assert callable(getattr(engine_obj, check_name))
