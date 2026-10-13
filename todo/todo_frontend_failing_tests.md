# Fix the 9 failing frontend (vitest) tests

## Status: ✅ Fixed 2026-10-13. Not a code bug: this checkout's `node_modules` was stale (`lottie-react` 2.4.1 installed, `package.json`/lockfile want 3.1.2). `npm ci` brought it back; vitest is now 40 files / 213 tests green. No repo change needed. CI was never affected (it runs `npm ci` then `npm test -- --run`).

`cd services/service_frontend && npx vitest run` → 3 files failed, 9 tests failed, 8 unhandled errors
(200 passed). Same result with and without the 2026-10-13 changes.

## Failures

| File | Failing | Symptom |
|---|---|---|
| `src/components/Core.test.jsx` | 8 tests (launcher ring: silhouettes, real buttons, toggle, taskbar selection; orbit rings: guest vs resident, dot per user/device/container, warning vs critical container, device reachability) | `TypeError: Cannot read properties of undefined (reading 'complete')` at `Core.jsx:603` |
| `src/App.test.jsx` | file fails to run | same error, thrown while rendering `Core` |
| `src/components/SituationalAwareness.test.jsx` | `renders the mood icon for the mood mode` | `expected null to be truthy`, a different cause |

## Leads

- `Core.jsx:603` reads `LottieSubscription.complete`, so `LottieSubscription` is `undefined` in the
  test environment. The tests most likely mock the Lottie package (or `lottie-react`) without that
  export, or the Lottie import changed (the intro-animation `subscriptions` prop). Fix the mock or
  guard the usage; check whether the intro actually works in the real build too.
- The mood-icon test probably looks up an icon that has changed (themed or swapped) since the test
  was written. Check what `SituationalAwareness.jsx` renders for `mood` now.

## Work items

- [ ] Find the commit that introduced the Lottie `subscriptions` usage and fix the test mock to match.
- [ ] Fix or update the mood-icon assertion.
- [ ] Confirm `npx vitest run` is green, then check whether CI runs the frontend tests (if it did,
      this would not have gone unnoticed); wire them in if not.

## Resolution

- `LottieSubscription` only exists in `lottie-react` v3 (the migration in `138dce52`, PR #195); the
  local install was still v2, so `Core` crashed in every test that rendered it, and the other
  failures came from the same stale install (including the mood-icon test).
- The leads above about a missing mock and a changed icon were wrong. Lesson: when only the local run
  fails, run `npm ci` before reading the code.
- Work items 1 and 2 are moot; item 3 is answered: CI already runs the frontend tests.
