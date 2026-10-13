# Frontend `npm run lint` crashes on startup

## Status: 🔲 Not started (found 2026-10-13). Fails identically on `main` before and after the 2026-10-13 dependency bumps.

`cd services/service_frontend && npm run lint` dies loading `eslint.config.js`:

    TypeError: reactHooks.configs.flat/recommended is not iterable

So the frontend has not been linted since `eslint-plugin-react-hooks` moved its flat config.
`lint.sh` and the pre-commit hooks call this, and AGENTS.md lists it as a required step.

## Work items

- [ ] Check the installed `eslint-plugin-react-hooks` version against its docs: newer majors expose
      `reactHooks.configs.flat.recommended` (an object, not an array), older ones
      `configs['recommended-latest']`. Spread/use it the way that version expects.
- [ ] Run lint, fix or consciously disable what it newly reports (it has not run for a while).
- [ ] Check CI: it runs `npm ci` and tests but not lint; consider adding a lint step once it works.
