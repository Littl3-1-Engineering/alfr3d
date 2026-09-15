# Plan: ALFR3D Cloud relay backend (Path C, Phase 3)

## Status: 🔲 TODO (not started — no code yet). Scoping session 2026-09-15 resolved the two open
questions Design §1/§2 originally flagged — see "Scoping update 2026-09-15" below before reading
the original Design section, which is kept but partially superseded.

## Scoping update 2026-09-15

**§2's login-convergence question is resolved: stay separate.** A Cloud subscriber's billing
login never doubles as a household member's `todo_auth_rbac.md` login — an admin manually pairs
a Cloud subscription to the local instance via a pairing code/token. Smaller blast radius if the
hosted side is ever compromised; the two systems don't need to know about each other.

**§1's relay/tunnel architecture question is resolved differently than originally sketched** —
researched whether to build on self-hosted Headscale (the household already runs vanilla
Tailscale successfully for the NUC, `alfr3d-gorsion` on `100.77.158.32`) rather than hand-rolling
a tunnel protocol from scratch. Verdict: **don't put unrelated paying households behind one
shared Headscale instance's ACL walls** — ruled out, not just deprioritized:

- Headscale's own docs state its scope directly: *"a single Tailscale network (tailnet),
  suitable for personal use, or a small open-source organisation"* — no official claim of safety
  for hosting mutually-untrusting third parties on one instance, which is exactly this product's
  shape.
- A live bug in exactly the area that matters here:
  [juanfont/headscale#2389](https://github.com/juanfont/headscale/issues/2389) — tag-based ACL
  changes don't take effect until the Headscale service restarts. For a subscription product,
  that means a canceled household could keep network access until the next restart — a real
  isolation-enforcement gap, not hypothetical.
- Headscale itself has a normal patch cadence for an actively maintained project —
  [CVE-2023-47390](https://www.wiz.io/vulnerability-database/cve/cve-2023-47390) (HIGH 7.5,
  bearer tokens logged in plaintext, fixed 0.23.0-alpha2), CVE-2025-47911/CVE-2025-58190 (fixed
  0.26.1), and [CVE-2026-46484](https://app.opencve.io/cve/CVE-2026-46484) (path
  traversal/auth-bypass in Headplane, a community Headscale web UI, letting an attacker rename
  any node/user record) — none disqualifying alone, but no reason to add exposure via a use case
  the project doesn't claim to support.
- The one "Headscale multi-tenant" writeup found
  ([ownding.com](https://ownding.com/2026/04/22/Headscale-Multi-Tenant-Transformation-Full-Isolation-of-ACL-Routes-DNS-and-More/))
  is an unaudited personal blog post with no linked source, no threat model, no security review —
  not something to hang this product's core privacy promise on.

**Two real options remain, both still WireGuard-based (keeps the "encryption is enforced by the
protocol, not by code we have to get right" property)**:

1. **Custom WireGuard hub relay (leaning toward this)** — one relay process, one WG interface,
   isolation enforced structurally via WireGuard's own `AllowedIPs` cryptokey routing (no ACL
   policy engine to misconfigure at all — each household's traffic literally cannot reach another
   household's subnet at the protocol level). Always-relay design (never attempts direct P2P), so
   no STUN/ICE/NAT-traversal code needed — acceptable bandwidth tradeoff for control-plane/push
   traffic, not video. Est. 2-4 weeks to build (peer provisioning API, dynamic `wg set` add/remove
   — no restart needed, unlike Headscale's tag-ACL bug above). Infra cost nearly flat as
   subscriber count grows (~$5-10/mo at launch, bandwidth-bound not instance-bound) since it's one
   shared process, not N deployments. Ongoing maintenance is our own code, but a narrow-scope
   service sitting on the WireGuard kernel module, which is small, mainline-audited, and rarely
   patched.
2. **One Headscale instance per tenant (fallback option)** — sidesteps the multi-tenant-ACL
   question entirely by having no shared ACL boundary: each subscriber gets their own isolated
   Headscale container. Less upfront build time (~1-2 weeks, leans on Headscale's own mature
   coordination/DERP-fallback/MagicDNS instead of hand-rolling routing), but operational cost
   scales in steps with subscriber count (a new container + SQLite DB + cert per household,
   patch/upgrade discipline across a growing fleet, each instance carrying Headscale's own CVE
   surface individually) — a real ongoing tax a small/solo team should weigh honestly against the
   custom build's higher one-time cost.

**Not fully locked** — leaning toward option 1 for its flatter long-term operational cost, but
this is close enough (2-4 weeks vs. 1-2 weeks upfront, both comfortably inside the $100/mo cap at
today's scale) that it's a real go/no-go for whoever picks this up next, not a settled decision.
Phase 0 below should resolve it with a real build, not more research.

## Scoping update 2026-09-15 (later, remote-device ingress)

The relay/tunnel decision above only covers the household↔relay leg. A separate question stayed
open until this same day: once a household is paired, how does *their own* remote phone or
browser — off the home network — actually reach the relay and get proxied home? Full build plan
(with diagrams) is in the artifact linked below; summary here for anyone not opening it.

Three options were weighed:

1. **A WireGuard peer per remote device** — reuses the relay verbatim, strongest possible privacy
   story, but browsers cannot run raw WireGuard. Only serves the `alfr3d_deck` app (via Android's
   `VpnService`), not the web dashboard — doesn't cover what this doc's own "Why this is needed"
   section promises ("remote access" generally, webapp included).
2. **Full TLS termination at the relay** (the actual Nabu Casa pattern) — ruled out, not just
   deprioritized. The relay would decrypt every household's traffic to route it, directly
   contradicting the "dumb pipe, never sees plaintext home data" claim already live on the
   pricing page. A truth-in-advertising problem, not an engineering tradeoff.
3. **SNI-passthrough proxy — decided.** The relay listens on :443 and reads only the TLS
   `ClientHello`'s SNI field to pick which household's WG tunnel to forward the *still-encrypted*
   bytes into. TLS termination stays exactly where it already is — the household's own nginx —
   so the relay never sees a decrypted byte, preserving the existing privacy claim while still
   giving a remote browser a plain HTTPS URL with no client software required. This also quietly
   covers `alfr3d_deck`'s own remote access for free: Deck is already just an HTTPS client, so
   "away from home" becomes a base-URL switch, not a new networking mode.

**Certificate handling — the one real new design decision inside option 3**: each paired
household's nginx gets its **own** ACME-issued cert, scoped only to its own
`<household-id>.relay.alfr3d.cloud` hostname, via HTTP-01 challenges proxied through the relay on
:80 the same way real traffic is proxied on :443. **Explicitly rejected**: one shared wildcard
cert (`*.relay.alfr3d.cloud`) issued once and pushed to every household — that would mean any
compromised household NUC holds a private key capable of impersonating *any other* household's
subdomain, a materially worse blast radius than anything the WireGuard isolation work above was
built to prevent.

Full plan, with a deployment diagram and a network/isolation diagram:
[Uplink Relay Plan](https://claude.ai/artifact/E9iMxSQUBRXfbw8iNwyLKY) (artifact, includes the
ingress decision in its own §05).

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

## Design (original sketch — §1/§2 superseded by "Scoping update 2026-09-15" above)

### 1. Relay/tunnel architecture — see the 2026-09-15 update above for the resolved direction
- A household's local `alfr3d` instance runs an **outbound-only tunnel client** (no inbound port
  forwarding required on the household network — matches the "never sees plaintext home data,
  dumb pipe" privacy claim already made publicly in the pricing copy).
- A hosted **relay server** accepts these outbound connections and proxies remote
  webapp/launcher traffic back to the household instance. Should not decrypt/inspect payloads
  beyond what's needed to route — end-to-end from client to household instance where possible.
  ~~How a remote device actually reaches the relay~~ — resolved 2026-09-15: SNI-passthrough
  proxy, not a WireGuard client on every device. See "Scoping update 2026-09-15 (later,
  remote-device ingress)" above.
- ~~Needs its own deploy/hosting decision~~ — resolved 2026-09-15: WireGuard-based (custom hub
  relay, leaning choice, or per-tenant Headscale as fallback), not a shared multi-tenant
  Headscale instance. See the update above for the full reasoning and cost comparison.

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
- ~~Open question~~ — resolved 2026-09-15: stay fully separate. A household admin manually links
  their Cloud subscription to their local instance via a pairing code/token; no shared login with
  `todo_auth_rbac.md`'s household user system. Smaller blast radius if the hosted side is ever
  compromised.

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
- **Phase 0 — architecture spike, now concrete**: build a minimal version of *both* remaining
  candidates from the 2026-09-15 update — (1) a bare custom WireGuard hub relay with dynamic
  `wg set` peer add/remove and (2) a single containerized per-tenant Headscale instance — against
  two fake households, confirm real cross-tenant isolation holds (household A's WG interface
  genuinely cannot reach household B's `AllowedIPs`), measure actual build time against the ~2-4
  week / ~1-2 week estimates above, and lock the final choice with a real result instead of more
  research. Also confirm the "dumb pipe" privacy claim holds under whichever is chosen (relay
  never sees anything past the WireGuard layer — the household's own HTTPS stays encrypted
  through it).
- **Phase 1 — subscriber identity + Stripe**: `subscribers` table, Checkout session creation,
  webhook handling, Customer Portal wiring.
- **Phase 2 — relay server + tunnel client**: the actual proxying infrastructure, now including
  the SNI-passthrough ingress proxy (:443) and its ACME HTTP-01 relay (:80) for per-household
  certs — see the 2026-09-15 remote-ingress update above.
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
