# Plan: Transactional Email Service (noreply sending, TOTP/OTP codes, registration, purchases)

## Status: 🔲 Not started

## Overview

No SMTP/email-sending capability exists anywhere in this codebase today (confirmed by grep during
`todo_auth_rbac.md`'s Phase 5 and again in `todo_onboarding_first_user.md` — zero hits either time).
That gap is already blocking two other todos in this directory (see Related), and will also block
transactional receipts once ALFR3D Cloud subscriptions exist. This todo tracks building one shared,
generic email-sending capability rather than solving it piecemeal inside each feature that needs it.

## Known use cases to design for

1. **Generic noreply transactional sending** — the actual capability every other use case below sits
   on top of: authenticate to a provider/SMTP relay and send a templated email from a `noreply@`
   sender identity. Everything else here is "what calls this," not a separate sending path.
2. **TOTP / one-time codes delivered by email** — the user's own explicit ask. Note: standard TOTP
   (RFC 6238, the Google-Authenticator-style rotating 6-digit code) is normally generated
   client-side from a shared secret and never emailed at all — if that's what's wanted, this todo
   isn't the dependency, a `pyotp`-style secret + QR-provisioning flow is, and doesn't need SMTP.
   What *does* need this email capability is an **emailed one-time code** (a short-lived code
   generated server-side and sent by email, sometimes loosely also called "OTP"/"TOTP" in casual
   use) — e.g. the "email OTP" step `todo_onboarding_first_user.md` already flagged as wanted
   right after first-run account claim/bootstrap. **Scoping question for whoever picks this up**:
   confirm with the user which of these two is actually meant before implementing — they're
   different features with different code paths (see Open Questions).
3. **User registration / account confirmation** — a welcome email on first-run bootstrap/claim
   (`todo_onboarding_first_user.md`) and/or on new resident creation (`todo_user_management.md`),
   so a household member has a real notification trail, not just an in-app state change.
4. **Purchases / billing receipts** — ties into the monetization plan (see Related): the Launcher
   Pro one-time unlock currently goes through Play Billing, which already sends its own Google
   Play receipt (no ALFR3D-side email needed there) — but ALFR3D Cloud subscriptions (Stripe,
   monetization Phase 3, not yet built) will need our own receipt/renewal/cancellation emails,
   since Stripe Checkout receipts alone aren't guaranteed to carry ALFR3D-specific context.
5. **Password reset** — `todo_auth_rbac.md`'s Phase 5 deliberately shipped an admin-assisted
   reset instead of an emailed reset link *because* this capability didn't exist yet. Once it
   does, revisit whether a self-service emailed-link reset is worth adding alongside (not
   required — the admin-assisted flow works fine for a household-scale app).

## Design sketch (needs a scoping pass before implementation)

- New `services/common/email_utils.py`, following the same pattern as `secrets_utils.py`/
  `ha_utils.py` — a small module other services import, not a new microservice. Should expose a
  generic `send_email(to, subject, template_name, context)`-shaped function so call sites don't
  each hand-roll MIME/provider calls.
- **Provider choice is the first real decision** (see Open Questions) — a raw SMTP relay
  (self-hosted or a mailbox provider's SMTP) vs. a transactional-email API (SendGrid, Postmark,
  AWS SES, Resend, etc). This should stay provider-swappable behind `email_utils`'s interface
  rather than hardcoding one vendor's SDK calls at every call site.
- Sender identity: `noreply@littl31.com` per the user's ask — requires domain-level setup (SPF/
  DKIM/DMARC records on `littl31.com`) regardless of provider choice, or the emails will land in
  spam/get rejected outright. This is a one-time domain-config task, not application code, but
  it's a hard prerequisite before any of this works end-to-end.
- Secrets: whatever API key/SMTP credential the chosen provider needs should go through
  `secrets_utils.py`'s existing encrypt-at-rest pattern (`todo_encrypt_secrets_at_rest.md`), not a
  new bespoke storage path.
- Templates: plain-text-first is fine for a v1 (registration/OTP/receipt content is short and
  functional, not marketing) — don't build an HTML template pipeline unless a concrete use case
  needs it.

## Open Questions

- **TOTP vs. emailed-OTP** (see use case 2 above) — which did the user actually mean? Confirm
  before implementing; they have different designs and only one needs this todo at all.
- **Provider choice and cost** — the monetization plan's Phase 0 budget cap is $100 total until
  the project earns revenue (see `[[alfr3d-monetization-plan]]`); most transactional-email
  providers have a free tier (Resend, SendGrid, AWS SES's pay-as-you-go pricing are all
  effectively free at this app's current household-scale volume) but this should be confirmed
  against current pricing at implementation time, not assumed stale from this note.
- **Self-hosted SMTP vs. third-party API** — a self-hosted relay avoids a vendor dependency but
  adds deliverability risk (cold IP reputation, more spam-filtering) and its own maintenance
  burden; a third-party transactional API is almost certainly the lower-effort/higher-reliability
  choice for a project this size, but flag this explicitly to the user rather than assuming.
- **Scope of v1** — does the first pass need to cover all five use cases above, or just enough to
  unblock `todo_onboarding_first_user.md`'s email-OTP step (the most concretely-wanted one right
  now)? Recommend scoping v1 to generic sending + whichever single use case is most wanted, not
  all five at once.

## Related

- `todo_onboarding_first_user.md` (this directory) — its "Follow-up: email OTP" step is blocked on
  this todo; that doc's Open Questions explicitly deferred the OTP vendor/scope decision here.
- `todo_auth_rbac.md` (this directory) — Phase 5's admin-assisted password reset was chosen
  specifically because this capability didn't exist; also documents the JWT/error-shape and
  household-trust-model conventions any new email-triggering endpoint should stay consistent with.
- `todo_encrypt_secrets_at_rest.md` (this directory) — wherever the chosen provider's credential
  gets stored should reuse `secrets_utils.py`, not a new storage path.
- `todo_user_management.md` (this directory) — a natural second call site (new-resident welcome
  email) once this capability exists.
- `[[alfr3d-monetization-plan]]` — ALFR3D Cloud (Path C, Phase 3) will need purchase/subscription
  receipt emails; the $100 pre-revenue budget cap documented there applies to any paid provider
  choice made here.
