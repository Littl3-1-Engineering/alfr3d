# Fix the 9 failing frontend (vitest) tests

## Status: 🔲 Not started (filed 2026-10-13). Already failing on a clean `main`; not caused by the disk-monitoring work.

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
