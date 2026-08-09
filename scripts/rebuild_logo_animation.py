#!/usr/bin/env python3
"""Rebuild the ALFR3D logo Lottie animation to match the littl31 logo's
animation craft (slow center "breathe-in", progressive draw-on, bounce easing,
and a whole-logo settle rotation) while keeping the existing filled-cyan
geometry.

The rebuilt file is written to every path given on the command line. Defaults
to the two places the animation ships today:
  - alfr3d frontend:  services/service_frontend/public/assets/lottie/logo.json
  - alfr3d launcher:  app/src/main/res/raw/alfr3d_logo.json

Run from the alfr3d repo root:
    python3 scripts/rebuild_logo_animation.py
"""

import json
import os
import sys

SOURCE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    os.pardir,
    "services",
    "service_frontend",
    "public",
    "assets",
    "lottie",
    "logo.json",
)

DEFAULT_OUTPUTS = [
    SOURCE,
    "/home/athos/Projects/Alfr3d/alfr3d_launcher/app/src/main/res/raw/alfr3d_logo.json",
]

CENTER = [420.0, 428.0]

# CSS-style cubic-bezier easing, given as (out, in) keyframe handles.
# lottie-web maps these to a BezierEasing([o.x, o.y, i.x, i.y]) per segment.
EASE_OUT = ((0.0, 0.0), (0.58, 1.0))  # cubic-bezier(0, 0, .58, 1) — fast start, decel
EASE_IN_OUT = ((0.333, 0.0), (0.667, 1.0))  # AE "easy ease"
LINEAR = ((0.0, 0.0), (1.0, 1.0))

FILL = [0.2, 0.709999952129, 0.898000021542, 1]


def build_keyframes(entries):
    """entries: list of (frame, value, ease|None). The last keyframe carries
    no handles, matching After Effects exports and lottie-web's per-keyframe
    easing lookup."""
    kfs = []
    for i, (t, val, ease) in enumerate(entries):
        k = {"t": t, "s": val}
        if ease is not None and i < len(entries) - 1:
            n = len(val)
            out_xy, in_xy = ease
            k["o"] = {"x": [out_xy[0]] * n, "y": [out_xy[1]] * n}
            k["i"] = {"x": [in_xy[0]] * n, "y": [in_xy[1]] * n}
        kfs.append(k)
    return kfs


def remap_times(keyframes, old_start, old_end, new_start, new_end):
    """Shift every keyframe time proportionally from the old window to a new one."""
    span = float(old_end - old_start)
    for kf in keyframes:
        frac = (kf["t"] - old_start) / span
        kf["t"] = new_start + frac * (new_end - new_start)


def make_trim(e_entries):
    return {
        "ty": "tm",
        "s": {"a": 0, "k": 0, "ix": 1},
        "e": {"a": 1, "k": build_keyframes(e_entries), "ix": 2},
        "o": {"a": 0, "k": 0, "ix": 3},
        "m": 1,
        "ix": 2,
        "nm": "Trim Paths 1",
        "mn": "ADBE Vector Filter - Trim",
        "hd": False,
    }


def draw_on_trim(start, end, ease=EASE_OUT):
    return make_trim([(start, [0], ease), (end, [100], None)])


def opacity_pop(start):
    """Transform opacity 0 -> 100 one frame before `start` so nothing is
    visible before its turn in the cascade."""
    return {
        "a": 1,
        "k": build_keyframes([(start - 1, [0], LINEAR), (start, [100], None)]),
        "ix": 7,
    }


def set_opacity(transform, start):
    transform["o"] = opacity_pop(start)


def set_static(prop):
    value = prop.get("k", [])
    if isinstance(value, list) and value and isinstance(value[0], list):
        value = value[0]
    return {"a": 0, "k": value}


def bounce_rotation(start, end, value):
    """Rotation with a littl31-style bounce: overshoot past rest, undershoot,
    settle. `value` is the starting angle (all shapes rest at 0)."""
    m1 = start + int(0.6 * (end - start))
    m2 = start + int(0.85 * (end - start))
    mag = abs(value)
    overshoot = round(0.12 * mag + 4.0, 1)
    undershoot = round(0.05 * mag + 2.0, 1)
    return build_keyframes(
        [
            (start, [value], EASE_IN_OUT),
            (m1, [overshoot if value < 0 else -overshoot], EASE_IN_OUT),
            (m2, [-undershoot if value < 0 else undershoot], EASE_IN_OUT),
            (end, [0], None),
        ]
    )


def smooth_rotation(start, end, value):
    return build_keyframes([(start, [value], EASE_OUT), (end, [0], None)])


def find_sub(items, ty):
    for it in items:
        if it.get("ty") == ty:
            return it
    return None


def find_shape(shapes, name):
    for s in shapes:
        if s.get("nm") == name:
            return s
    raise KeyError("shape not found: " + name)


def main():
    with open(SOURCE) as f:
        data = json.load(f)

    layer = data["layers"][0]
    shapes = layer["shapes"]

    if any(s.get("nm") == "Logo (settle)" for s in shapes):
        sys.exit(
            "SOURCE is already rebuilt. Restore the pristine logo.json "
            "(git checkout) before re-running."
        )

    # --- Dot: slow 1.2s "breathe-in" (frames 0-36) ---
    dot = find_shape(shapes, "Dot")
    dot_tr = find_sub(dot["it"], "tr")
    dot_tr["s"] = {
        "a": 1,
        "k": build_keyframes([(0, [0, 0], EASE_OUT), (36, [100, 100], None)]),
        "ix": 3,
    }

    # --- Wedge-rt: replace scale pop with draw-on ---
    w = find_shape(shapes, "Wedge-rt")
    w_tr = find_sub(w["it"], "tr")
    w_tr["s"] = {"a": 0, "k": [100, 100], "ix": 3}
    w["it"].insert(1, draw_on_trim(40, 50))
    set_opacity(w_tr, 40)

    # --- Wedge-tl-3: smooth rotation, animated trim draw-on ---
    w = find_shape(shapes, "Wedge-tl-3")
    w_tr = find_sub(w["it"], "tr")
    w_tr["r"] = {"a": 1, "k": smooth_rotation(52, 64, 26), "ix": 6}
    tm = find_sub(w["it"], "tm")
    tm["e"] = draw_on_trim(52, 64)["e"]
    set_opacity(w_tr, 52)

    # --- Wedge-r: bounce rotation + draw-on ---
    w = find_shape(shapes, "Wedge-r")
    w_tr = find_sub(w["it"], "tr")
    w_tr["r"] = {"a": 1, "k": bounce_rotation(52, 64, -70), "ix": 6}
    w["it"].insert(1, draw_on_trim(52, 64))
    set_opacity(w_tr, 52)

    # --- Rad-t / Rad-tr-i: retime existing band trims + opacity ---
    for name, new_start, new_end in (("Rad-t", 52, 64), ("Rad-tr-i", 52, 64)):
        s = find_shape(shapes, name)
        s_tr = find_sub(s["it"], "tr")
        for prop in ("s", "e", "o"):
            p = find_sub(s["it"], "tm")[prop]
            if p["a"] == 1:
                remap_times(p["k"], 50, 59, new_start, new_end)
        set_opacity(s_tr, new_start)

    # --- Rad-br / Wedge-bl-2 ---
    s = find_shape(shapes, "Rad-br")
    s_tr = find_sub(s["it"], "tr")
    for prop in ("s", "e", "o"):
        p = find_sub(s["it"], "tm")[prop]
        if p["a"] == 1:
            remap_times(p["k"], 70, 92, 66, 80)
    set_opacity(s_tr, 66)

    w = find_shape(shapes, "Wedge-bl-2")
    w_tr = find_sub(w["it"], "tr")
    w_tr["r"] = {"a": 1, "k": smooth_rotation(66, 80, -123), "ix": 6}
    w["it"].insert(1, draw_on_trim(66, 80))
    set_opacity(w_tr, 66)

    # --- Rad-tr-o: replace scale with draw-on ---
    s = find_shape(shapes, "Rad-tr-o")
    s_tr = find_sub(s["it"], "tr")
    s_tr["s"] = {"a": 0, "k": [100, 100], "ix": 3}
    s["it"].insert(1, draw_on_trim(82, 92))
    set_opacity(s_tr, 82)

    # --- Rad-bl-o (band trim) / Wedge-bl-1 (smooth rotation + draw-on) ---
    s = find_shape(shapes, "Rad-bl-o")
    s_tr = find_sub(s["it"], "tr")
    for prop in ("s", "e", "o"):
        p = find_sub(s["it"], "tm")[prop]
        if p["a"] == 1:
            remap_times(p["k"], 95, 106, 88, 100)
    set_opacity(s_tr, 88)

    w = find_shape(shapes, "Wedge-bl-1")
    w_tr = find_sub(w["it"], "tr")
    w_tr["r"] = {"a": 1, "k": smooth_rotation(88, 100, -33), "ix": 6}
    w["it"].insert(1, draw_on_trim(88, 100))
    set_opacity(w_tr, 88)

    # --- Wedge-tl-2: bounce rotation + draw-on ---
    w = find_shape(shapes, "Wedge-tl-2")
    w_tr = find_sub(w["it"], "tr")
    w_tr["r"] = {"a": 1, "k": bounce_rotation(98, 112, 25), "ix": 6}
    w["it"].insert(1, draw_on_trim(98, 112))
    set_opacity(w_tr, 98)

    # --- Rad-tl (band trim) / Wedge-tl-1 (bounce rotation + draw-on) ---
    s = find_shape(shapes, "Rad-tl")
    s_tr = find_sub(s["it"], "tr")
    for prop in ("s", "e", "o"):
        p = find_sub(s["it"], "tm")[prop]
        if p["a"] == 1:
            remap_times(p["k"], 115, 128, 110, 126)
    set_opacity(s_tr, 110)

    w = find_shape(shapes, "Wedge-tl-1")
    w_tr = find_sub(w["it"], "tr")
    w_tr["r"] = {"a": 1, "k": bounce_rotation(110, 126, 18), "ix": 6}
    w["it"].insert(1, draw_on_trim(110, 126))
    set_opacity(w_tr, 110)

    # --- Rad-bl-i: replace scale with draw-on ---
    s = find_shape(shapes, "Rad-bl-i")
    s_tr = find_sub(s["it"], "tr")
    s_tr["s"] = {"a": 0, "k": [100, 100], "ix": 3}
    s["it"].insert(1, draw_on_trim(124, 136))
    set_opacity(s_tr, 124)

    # --- Wrap everything in a parent group that settles -5deg -> 0 ---
    parent_transform = {
        "ty": "tr",
        "p": {"a": 0, "k": CENTER, "ix": 2},
        "a": {"a": 0, "k": CENTER, "ix": 1},
        "s": {"a": 0, "k": [100, 100], "ix": 3},
        "r": {
            "a": 1,
            "k": build_keyframes(
                [
                    (138, [-5.0], EASE_IN_OUT),
                    (146, [1.2], EASE_IN_OUT),
                    (149, [-0.4], EASE_IN_OUT),
                    (152, [0.0], None),
                ]
            ),
            "ix": 6,
        },
        "o": {"a": 0, "k": 100, "ix": 7},
        "sk": {"a": 0, "k": 0, "ix": 4},
        "sa": {"a": 0, "k": 0, "ix": 5},
        "nm": "Transform",
    }
    children = shapes
    parent = {
        "ty": "gr",
        "it": children + [parent_transform],
        "nm": "Logo (settle)",
        "np": len(children),
        "cix": 2,
        "bm": 0,
        "ix": 1,
        "mn": "ADBE Vector Group",
        "hd": False,
    }
    layer["shapes"] = [parent]

    # Cut the dead tail: build ends at 152, settle, then hold until 165
    # (was 180). Both the top-level and layer out-points must move together so
    # the layer never ends before the animation's total duration.
    data["op"] = 165
    layer["op"] = 165

    outputs = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_OUTPUTS
    blob = json.dumps(data)
    for out in outputs:
        with open(out, "w") as f:
            f.write(blob)
        print("wrote %s (%d bytes)" % (out, len(blob)))

    # Sanity report
    report = []
    for kf in layer["shapes"][0]["it"][1]["it"]:
        pass
    report.append("op = %s" % layer["op"])
    report.append("parent group: %s children + settle transform" % len(children))
    print("summary:", ", ".join(report))


if __name__ == "__main__":
    main()
