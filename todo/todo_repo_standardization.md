# Todo: Bring All 3 Project Repos to the Same Tooling Standard

## Status: 🔲 Not started

## Scope
Applies to all three repos: `alfr3d` (this repo), `alfr3d_deck`, and `littl31`. This continues the existing effort to keep the three repos consistent (see `AGENTS.md`/`CLAUDE.md` structure, which was already standardized across all three).

## Current state (as of writing)
- `alfr3d` already has `.pre-commit-config.yaml` and `.github/dependabot.yml`.
- `alfr3d_deck` and `littl31` — status unconfirmed, likely missing one or both.
- Aikido (security scanning) — not yet set up in any of the three repos.

## Tasks
- [ ] Audit each repo for: pre-commit hooks, Dependabot config, Aikido security scanning, and any other baseline tooling (CI lint/test/build workflow, license file, etc.).
- [ ] Bring `alfr3d`'s `.pre-commit-config.yaml` and `.github/dependabot.yml` to `alfr3d_deck` and `littl31`, adapted per-language (Kotlin/Gradle for `alfr3d_deck`, whatever `littl31`'s stack is).
- [ ] Set up Aikido across all three repos.
- [ ] Confirm each repo has a CI workflow (alfr3d already has `.github/workflows/ci.yml` per `todo/optimizations_v2.md`) — add to the other two if missing.
- [ ] Document the standard tooling checklist somewhere durable (README or AGENTS.md Core Rules) so future new repos start from the same baseline.

## Related
- Companion file: none yet in `alfr3d_deck`/`littl31` `todo/` — this file is the canonical tracker; add pointer stubs there if work gets close to repo-specific enough to split.
