# Kanji wisdom quotes — corner-of-screen visual (Deck + web frontend)

## Status: not started (added 2026-10-03); cross-repo, mirrored in `alfr3d_deck/todo/`

Ask: add visuals to **Alfr3d Deck** and the **Alfr3d web frontend** that show wise quotes in
**kanji script** in some corner of the screen.

## Notes / decisions to make

- Corner placement and rotation cadence (per-launch, hourly, daily?). Must not collide with the
  HUD rings / Socket / orbit nodes (see `todo_cyber_hud_buttons_frontend.md`).
- Entries may be proverbs **or single words/concepts** (e.g. 独り占め) — the layout must handle both a one-word and a full-sentence entry.
- Quote source: curated local list (kanji + reading + translation) vs LLM-generated. Recommendation:
  curated list, since a misrendered or wrong kanji is worse than a repeated quote.
- Vertical (tategaki) vs horizontal layout; needs a CJK-capable font on both surfaces (Noto Serif/Sans JP)
  — check bundle size on Android and the web build.
- Style: cyan, low-opacity, subtle glitch/scramble reveal consistent with the HUD vocabulary. Respect reduced-motion.
- Optional: tap/click reveals reading + translation.

## Candidate entries

Curated list (kanji + reading + translation). Each entry should be checked by a Japanese reader
before shipping, per the "wrong kanji is worse than a repeated quote" rule above.

| Kanji | Reading | Meaning | Notes |
|---|---|---|---|
| 独り占め | hitorijime | keeping something all to oneself; monopolizing, hogging | Added 2026-10-04 on request. A vocabulary word, not a proverb — fine: the list allows single words/concepts as well as proverbs (decided 2026-10-04). |
