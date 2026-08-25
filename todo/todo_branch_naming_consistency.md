# Todo: Consistent Main-Branch Naming Across All 3 Repos

## Status: ✅ Done (2026-08-25) — `alfr3d`'s `Neural-Blueprint`/`main` split resolved itself via
PR #108 (fully merged, `main` is now the active branch) before this todo was acted on;
`littl31` renamed `master`→`main` via GitHub API in the same repo-hygiene pass. All three
repos now default to `main`. `Neural-Blueprint` itself was deliberately left in place
(not deleted) per explicit instruction — it's just no longer the active development branch.

## Goal

Pick one convention -- `main` or `master` -- and make all three repos (`alfr3d`, `alfr3d_deck`,
`littl31`) use it for their primary branch, the same way `AGENTS.md`/`CLAUDE.md` structure and the
`.pre-commit-config.yaml` baseline are already kept consistent across the three (see
`todo_repo_standardization.md`).

## Current state (confirmed 2026-08-24; see Status above for 2026-08-25 resolution)

- **`alfr3d_deck`**: `main`, no issue. Single branch, GitHub default is `main`, CI
  (`.github/workflows/build.yml`) already triggers on `branches: [main]`. Nothing to do here.
- **`littl31`**: `master`, no issue *internally* (GitHub default is `master`, `deploy.yml` triggers
  on `branches: [master]`), but it's the odd one out relative to the other two.
- **`alfr3d`**: the real problem, and it's bigger than naming. GitHub's default branch is `main`,
  but **all actual development happens on a differently-named branch, `Neural-Blueprint`**, which
  is 260+ commits ahead of `main` (`main` is stale, last real commit there predates the current
  session by a wide margin). `ci.yml` triggers on `branches: [main]` -- meaning CI's lint/test/build
  gate **never actually runs against the branch anyone pushes real work to**. This is the same class
  of problem `todo_repo_standardization.md` already flagged for the CI-was-disabled issue, just a
  different mechanism (wrong branch trigger instead of a `.disabled` suffix) with the same effect:
  the safety net isn't actually catching anything.

## Notes / Approach

1. **Decide the convention.** Recommend `main`: two of three repos already use it as their nominal
   default (`alfr3d_deck` fully consistently; `alfr3d`'s stale default is still technically `main`),
   and it's GitHub's modern default for new repos. This makes `littl31` the only repo that needs a
   rename, not two.
2. **`littl31`**: rename `master` -> `main` (GitHub Settings > Branches has a one-click rename that
   auto-redirects PRs and updates branch protection rules -- confirm it actually moved everything
   before deleting the old name). Update `deploy.yml`'s `branches: [master]` trigger. Check
   `package.json`'s `release` script (`gh-pages -d dist -b live`) and anything else that might
   assume `master` by name. Re-point local clones (`git branch -m master main`,
   `git fetch origin`, `git branch -u origin/main`).
3. **`alfr3d`** (the harder one): decide whether `Neural-Blueprint` should be merged/fast-forwarded
   into `main` (making `main` the real branch again) or renamed to become the new `main` outright
   (retiring the stale old `main`). Either way, once resolved: confirm `ci.yml`'s `branches: [main]`
   trigger actually fires on real pushes going forward, and update the several `blob/Neural-Blueprint/...`
   source links currently in the Notion Alfr3d Timeline database and `littl31/src/assets/data/timeline.json`
   (added because `Neural-Blueprint` was the only branch those files actually existed on at time of
   writing) to point at whatever branch name wins.
4. **All three**: after renaming/reconciling, double check branch protection rules reference the
   right branch name, and grep each repo's own docs (README, AGENTS.md/CLAUDE.md, todo files) for
   hardcoded branch names in links.

## Open Questions

- Is `Neural-Blueprint` a deliberate long-lived branch (e.g. some kind of staging/dev split from
  `main`), or just accidental drift where work never got merged back? This changes whether item 3
  above is a merge or a rename -- needs the user's call before touching it, not an assumption.

## Related

- `todo_repo_standardization.md` (this directory) -- the existing cross-repo tooling-consistency
  effort this todo extends into branch naming; also the origin of the "CI not actually running
  against real work" pattern this todo repeats in a different form.
