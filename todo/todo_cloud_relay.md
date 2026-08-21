# Plan: ALFR3D Cloud relay backend (Path C, Phase 3)

## Status: 🔲 TODO (not started — planning only, added 2026-08-21)

## Goal
Give the monetization plan's "Phase 3 — Build ALFR3D Cloud" line item (currently just an unscoped
bullet: "outbound tunnel client, relay server, accounts/auth, Stripe subscriptions, push via FCM")
a real design doc, the same treatment `todo_auth_rbac.md` already gave household auth. This is the
backend counterpart to the site-facing `littl31/todo/todo_cloud_kit_commerce.md` Phase C — that doc
covers Stripe Checkout + Customer Portal + login UI on littl31.com; this doc covers what has to
exist server-side for any of that to work.

## Current state (verified 2026-08-21)
- No relay or cloud service exists anywhere in this repo — confirmed via filename search
  (`*relay*`, `*cloud*` return zero results) and by reading `services/` directly. The seven
  existing services (`service_api`, `service_daemon`, `service_user`, `service_device`,
  `service_environment`, `service_speak`, `service_frontend`) are all local/self-hosted household
  services; none of them talk to the internet on behalf of a hosted product.
- No Stripe/billing/payment code exists anywhere (grepped repo-wide for
  "stripe|billing|subscription|checkout" — all matches were unrelated false positives). Nothing in
  `requirements.txt` mentions Stripe, FCM, or Firebase.
- `service_user` + `services/service_api/routes/users.py` is a **household presence tracker**
  (who's home/online), not a customer/subscriber identity system — see `todo_auth_rbac.md` for why
  that's a distinct concern from what this doc needs.
- `todo_auth_rbac.md` (this same directory) is the only existing scoping for any accounts/auth
  work, and it's explicitly about **household API access** (JWT + roles: technoking/resident/guest
  controlling devices/routines/calendar/music) — not customer billing identity. This doc's
  subscriber-accounts section below must stay distinct from that one, though the two may eventually
  share a login layer (see Design §2 below).

## Why this is needed
Per the monetization plan (project memory `alfr3d-monetization-plan`): ALFR3D Core (the backend)
stays free, self-hosted, local-first forever — it is not the product being sold. **ALFR3D Cloud**
is the actual revenue engine: a thin hosted relay (dumb pipe, never sees plaintext home data) that
gives remote access + push notifications without compromising the local-first/no-telemetry
positioning both repos hold to. Priced at free / $5.99mo (Cloud) / $11.99mo (Cloud+, adds hosted
backups + LLM personality features + priority support), benchmarked against Nabu Casa. This is
Phase 3 of that plan — the highest-effort, highest-payoff phase, not yet started.

## Design

### 1. Relay/tunnel architecture
- A household's local `alfr3d` instance runs an **outbound-only tunnel client** (no inbound port
  forwarding required on the household network — matches the "never sees plaintext home data,
  dumb pipe" privacy claim already made publicly in the pricing copy).
- A hosted **relay server** accepts these outbound connections and proxies remote
  webapp/launcher traffic back to the household instance. Should not decrypt/inspect payloads
  beyond what's needed to route — end-to-end from client to household instance where possible.
- Needs its own deploy/hosting decision (out of scope for this doc to pick a specific cloud
  provider — flag as an open question, informed by the $100 budget cap: free-tier-friendly options
  should be evaluated first).

### 2. Subscriber accounts/auth — customer/billing identity, not household RBAC
- This is **not** the same system as `todo_auth_rbac.md`'s household users (technoking/resident/
  guest). That system answers "can this person control the living room lights." This system
  answers "does this household have an active Cloud subscription, and which relay
  connection/tenant does it map to."
- Minimal viable model: a `subscribers` table (email, Stripe customer ID, active tier, relay
  tenant/household identifier) — deliberately not reusing the existing `user`/`user_types` tables
  from `setup/createTables.sql`, since a Cloud subscriber is a billing relationship with a
  household as a whole, not an individual household member.
- Login: per the site-facing doc's recommendation, use something lightweight (e.g. passwordless
  magic-link email) for the website account/billing UI, backed by this subscriber identity store.
- **Open question, flag for the user rather than assume**: should a Cloud subscription's login
  ever double as a household member's login (i.e., converge with `todo_auth_rbac.md`'s user
  system), or should the two stay fully separate (a household admin manually links their Cloud
  subscription to their local instance via a pairing code/token, with no shared login at all)? The
  latter is simpler and keeps the relay's blast radius smaller if the hosted side is ever
  compromised — recommend defaulting to that unless the user wants a unified login.

### 3. Stripe subscription integration
- Stripe Checkout for signup (session created by whatever serverless/backend endpoint the
  site-facing doc's Phase C ends up using).
- Webhook handler here (relay server or a small adjacent service) to react to
  `customer.subscription.{created,updated,deleted}` and payment-failure/dunning events — activate
  or revoke relay access accordingly.
- Stripe Customer Portal (see site-facing doc) handles the self-service UI; this backend only needs
  to consume Stripe's webhooks, not build billing UI.

### 4. Push via FCM
- Cloud+ tier and general remote-notification use cases need server-initiated push to the
  `alfr3d_deck` Android launcher. Needs a service account / FCM project setup and a thin
  send-notification path from the relay (or a service behind it) to FCM.

### 5. Rollout phasing (mirrors `todo_auth_rbac.md`'s phasing style)
- **Phase 0 — architecture spike**: pick relay hosting, prototype the outbound-tunnel client
  against a minimal echo relay, confirm the "dumb pipe" privacy claim holds under the actual
  chosen transport (e.g. is TLS terminated at the relay or passed through end-to-end).
- **Phase 1 — subscriber identity + Stripe**: `subscribers` table, Checkout session creation,
  webhook handling, Customer Portal wiring.
- **Phase 2 — relay server + tunnel client**: the actual proxying infrastructure.
- **Phase 3 — FCM push**.
- **Phase 4 — security review before public launch** (the monetization plan already flags this as
  a $1,500–5,000 line item, deferred under the $100 cap until there's revenue — do a DIY/self-review
  pass first, matching how the Phase 0 licensing/trademark work was handled).

## Related
- `littl31/todo/todo_cloud_kit_commerce.md` — the site-facing half (Checkout UI, Customer Portal
  embed, waitlist capture) that Phase 1 above needs to plug into.
- `todo_auth_rbac.md` (this directory) — household API access auth; explicitly a separate system,
  cross-referenced above at Design §2.
- Project memory `alfr3d-monetization-plan` — Path C pricing, phase ordering, $100 budget cap.
