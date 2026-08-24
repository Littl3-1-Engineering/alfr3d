# Todo: Bring All 3 Project Repos to the Same Tooling Standard

## Status: 🟡 alfr3d_deck done 2026-08-24; littl31 and Aikido still open

## Scope
Applies to all three repos: `alfr3d` (this repo), `alfr3d_deck`, and `littl31`. This continues the existing effort to keep the three repos consistent (see `AGENTS.md`/`CLAUDE.md` structure, which was already standardized across all three).

## Current state (as of 2026-08-24)
- `alfr3d`: has `.pre-commit-config.yaml` and `.github/dependabot.yml`. **Correction**: this todo previously claimed `alfr3d` "already has `.github/workflows/ci.yml`" per `todo/optimizations_v2.md` — that file is actually `ci.yml.disabled`, i.e. not active. Not investigated/fixed this pass (out of scope for the alfr3d_deck work below); worth its own look at why it's disabled.
- `alfr3d_deck`: **done**. Added `.pre-commit-config.yaml` (pre-commit-hooks generic set + detect-secrets, adapted from alfr3d's — dropped black/flake8 since there's no Python here) and `.github/dependabot.yml` (`gradle` + `github-actions` ecosystems, the latter not present in alfr3d's own dependabot config — a possible follow-up there too). Generated `.secrets.baseline` via a throwaway venv (repo's own `detect-secrets` CLI install was broken — `ModuleNotFoundError`). One flagged finding: `keystore.properties.sample`'s `changeme` placeholder values, expected/safe. Already had CI (`build.yml`, `release.yml`) — ahead of alfr3d on that front. Did **not** add ktlint/detekt (Kotlin lint) — would need Gradle build-file wiring and tuning against the existing codebase, more invasive than this pass's scope; left as a follow-up.
- Running `pre-commit run --all-files` against `alfr3d_deck` also auto-fixed 7 pre-existing files missing a trailing newline (six `app/src/main/play/*` text files + `.gitignore` + `SearchPanel.kt`) — trivial single-line diffs, kept as part of adopting the hook rather than reverted.
- `littl31`: not touched this pass.
- Aikido (security scanning): not yet set up in any of the three repos — needs an external account signup, which isn't something that can be done unattended; still open for whoever has/creates the account.

## Tasks
- [x] Audit each repo for: pre-commit hooks, Dependabot config, Aikido security scanning, and any other baseline tooling (CI lint/test/build workflow, license file, etc.).
- [x] Bring `alfr3d`'s `.pre-commit-config.yaml` and `.github/dependabot.yml` to `alfr3d_deck`, adapted per-language.
- [ ] Same for `littl31` (whatever its stack is).
- [ ] Set up Aikido across all three repos (needs account signup first).
- [ ] Figure out why `alfr3d`'s own CI workflow is `.disabled` and either fix or remove it.
- [ ] Consider ktlint/detekt for `alfr3d_deck` as a separate, scoped pass.
- [ ] Document the standard tooling checklist somewhere durable (README or AGENTS.md Core Rules) so future new repos start from the same baseline.

## Related
- Companion file: `alfr3d_deck/todo/todo_repo_standardization.md` — pointer stub, unchanged.
