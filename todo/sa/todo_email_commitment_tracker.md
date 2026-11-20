# SA: Email as a commitment tracker (SPEC ONLY)

> **Layer:** L1 learner + consumer · **Roadmap:** [SA_ROADMAP.md](SA_ROADMAP.md) "Intimate Butler" item 3 of 5 · **Notion:** Alfr3d Timeline row "Email as a commitment tracker" (Planned)
> **Prompt:** "card feedback, close SA gaps, start the next steps" (2026-11-14), Phase 4: spec only, with a retention schedule for stored subjects, one-click export and delete, and the rule that bodies are never requested. Ask before widening what is read.

## Status: spec written 2026-11-20. Nothing built. Needs the owner's decisions in the last section before E0.

The idea: Gmail metadata is already captured (3,656 messages over 12 months at the Notion row's last
count). Turn it into one useful thing: "this person is waiting on a reply from you" and "you are waiting
on them", learned per sender, without ever reading what a message says.

## Phase 0 findings (read from the code, 2026-11-20)

1. **The Gmail scope does not enforce "metadata only".** `gmail_utils.SCOPES` and `setup/authorize_google.py`
   request `gmail.readonly`, which can read bodies and attachments. "Bodies are never requested" is a
   convention in code, not a property of the grant.
2. **The claim is false for the card path.** `gmail_utils.check_unread_emails()` (used by the `email` card,
   `health_cards.check_emails`) calls `messages().get(userId="me", id=...)` with no `format`, and the Gmail
   default is `full`: the whole message, body included, comes back for up to 5 unread messages each cycle.
   The code keeps only `From` and `Subject` and drops the rest, but it *is* requested. The lake path
   (`sa/email_log.py`) is correct: `format="metadata"`, `metadataHeaders=["From","Subject","Date"]`.
   Notion's "body never requested" is true of the lake and not of the card.
3. **Gmail returns a short `snippet` (the start of the body) in every format, metadata included.**
   `email_log.parse_message` does not keep it. Nothing asserts that.
4. **Stored today:** bronze `email_messages` Parquet on the NUC lake volume: `message_id, thread_id,
   received_utc, sender_name, sender_email, sender_domain, subject, labels, is_unread, size_estimate`.
   Silver `email_events` carries all of it; gold `email_hourly` holds counts by category.
5. **No retention on subjects.** The 365-day `EMAIL_BACKFILL_DAYS` only limits what is *fetched*. Nothing
   deletes or blanks a stored message (the only removal is `purge_implausible`, for bad dates), so
   subject lines and sender addresses are kept indefinitely.
6. **Nothing reads the subject.** Learners read gold counts only (`rates.py`: `email/all`, `/promotions`,
   `/updates`); `subject` is only carried through the silver view.
7. **One mailbox, no owner.** A single `integrations_tokens` row (`google`) serves the whole household; the
   data is not tied to a person. Commitments in someone's inbox are personal.
8. **No export and no delete path exists** for email data (the lake has export-in, never out).
9. **The self-healing sync would undo a delete.** Each run lists the whole 365-day window and fetches every
   message id not already stored, so deleting stored rows makes the next run re-download them.

## Invariants (hold for every phase)

- **Metadata only, bodies never requested.** No `format=full` or `raw`, no attachments, no `snippet`
  stored, no body-derived feature of any kind. Widening is an owner decision (below), never a default.
- **Local.** Extraction and learning stay on the NUC. Nothing is sent anywhere, no cross-household use.
- **Read-only toward the mailbox.** Alfr3d never sends, drafts, labels, archives or deletes mail. The tracker
  surfaces; the owner acts. (Level 0 of the autonomy ladder, and no email action type exists.)
- **Degrade to silence.** No credentials, no history for a sender, or insufficient evidence: no card.
- **Observation, never concern.** "Sam wrote on Tuesday and there is no reply from you" and nothing about
  what that should make anyone feel.
- **Inspectable and resettable.** Everything learned from email shows in Teach-me and can be reset.

## What "commitment" means without reading anything

Only structure that metadata already carries: `thread_id`, the `SENT` / `INBOX` labels (who spoke last),
timestamps, category labels, and the sender. Three tiers, each gated:

| tier | signal | reads | status |
|---|---|---|---|
| **1: thread state** | last message in a thread is inbound from a person (not promotions/updates/social/forums), older than N hours, with no later `SENT` in the thread: "awaiting your reply". The reverse, last message is yours and no answer after N days: "awaiting theirs". | headers already stored | in this spec |
| **2: subject cues** | a deadline or question in the subject line ("by Friday", "?"), extracted locally | subject text, already stored | **needs the owner's approval**; off by default |
| **3: body** | anything from the message text | the body | **out of scope.** Needs a scope change, an explicit opt-in and its own spec |

Tier 1 is enough to be useful and is the only tier proposed for building.

## Design (tier 1)

- **Gold `email_threads`** (derived, rebuilt nightly, no subject, no body): `thread_id`, `n_messages`,
  `last_inbound_utc`, `last_outbound_utc`, `last_speaker`, `counterpart_key`, `category`. Registered in the
  context registry so the ledger shows its capture start, coverage and retention.
- **Sender importance learner** (per `counterpart_key`): frequency counts, no black box. P(owner replies
  | sender writes a person-category thread) and the median reply latency, as a Beta-Binomial with sample
  floors and an explicit "insufficient evidence" outcome. Held-out validation is time-blocked, as in the
  covariate engine. It is the evidence for "this sender usually gets a reply, and this one went quiet".
- **Card feedback closes the loop.** `acked` is a mild positive, `not_useful` the only clear negative
  (existing semantics); a `not_useful` on a sender lowers that sender's weight. Needs the card-feedback
  counts to grow first (about 6 explicit interactions so far), so the sender prior comes from observed
  reply behaviour, and feedback only adjusts it.
- **No new card.** The existing `email` card (priority 4) gains an "awaiting your reply" variant in its
  slot, so `MAX_DISPLAYS == 26` is untouched. Its wording is shown to the owner before it is written.
- **Outcome label** (Layer 3 1/4 vocabulary): a reply in the thread after the card is *acted on*;
  `not_useful` is *rejected*; nothing is *ignored*. No outcome ever acts on mail.

## Retention schedule for stored subjects (required before anything widens)

Proposed defaults (owner chooses; see decisions):

| data | where | keep | after that |
|---|---|---|---|
| subject line | bronze + silver `email_events` | **90 days** | set to NULL (tombstone, row kept) |
| `sender_name` | same | 90 days | NULL |
| `sender_email` | same | 90 days | replaced by an HMAC key (local secret), so per-sender learning still works without an address on disk; `sender_domain` stays |
| structure columns (ids, times, labels, size) | bronze | 730 days (like every SA table) | row deleted |
| `email_threads`, sender profiles | gold / `sa_profiles` | rebuilt from the above; a profile expires 365 days after the sender was last seen | deleted |

Mechanics: a nightly `email_retention` stage in `sa-learner`, idempotent, frozen-clock tested, reporting
counts to the log and the ledger. It **tombstones rather than deletes** within the 365-day window: a
blanked row stays stored by `message_id`, so the self-healing sync (finding 9) does not fetch the subject
again. Retention never touches Gmail. A stored-subject age check goes in the ledger, so "is anything
about to be kept past its schedule" is visible.

## One-click export and delete

Owner-only (the same gate as the Teach-me route in PR #462: `technoking`). UI after the contract is reviewed.

- `GET /api/integrations/email/export`: everything stored about email, as one file: bronze rows, derived
  thread rows, sender profiles and inferences. Never tokens. The same shape the owner would see in
  Teach-me, plus the raw rows.
- `DELETE /api/integrations/email/data` with an explicit confirm parameter: removes bronze, silver and gold
  email data and the email profiles and inferences, **pauses email sync** (a stored `email_sync_paused`
  flag, so finding 9 cannot refill it), and returns row counts per store. Re-enabling is a separate
  deliberate step. Disconnecting the Google account (revoking the token) is its own action and is
  not implied by delete.
- **Verification:** a test that, after delete, every store reads zero, the next sync run fetches nothing,
  and `email_hourly` rebuilds empty. A live check on a throwaway lake before it ships.

## Bodies never requested: how it is enforced, not just promised

1. **Fix the card path** (`gmail_utils.check_unread_emails`): `format="metadata"` and
   `metadataHeaders=["From","Subject"]`. A narrowing, not a widening.
2. **One door.** All Gmail message reads go through one function that fixes the format and the header
   allow-list. A static test fails the build if any other `messages().get` appears, if a format other than
   `metadata` is used, or if `snippet` reaches a stored column.
3. **A scope that cannot read bodies (optional).** `gmail.metadata` makes the guarantee structural, but the
   documented limitation is that it does not support the `q` search parameter the sync uses (`after:...`),
   so the sync would page by label and filter by date locally. Changing scope also forces a re-authorise.
   Verify on a throwaway Google account before relying on it.

## What needs the owner's approval before it is read (the "ask before widening" list)

Each is off until approved, one at a time: subject-text analysis (tier 2); the `To` / `Cc` headers (they
separate "addressed to you" from "copied", which matters for obligation); any message text or snippet
(tier 3, out of scope); other household members' mailboxes; attachments (never proposed); a write scope
(never proposed).

## Phases (when approved; each ends with a gate)

- **E0: safety prerequisites, no learning.** Card-path format fix; one-door wrapper and the static test;
  `email_retention` stage and ledger entry; export and delete routes with the pause flag. *Gate:* delete
  proven on a throwaway lake; retention proven with a frozen clock; CI green. Nothing below starts first.
- **E1: thread state (no card).** Gold `email_threads`; a replay over the stored year measuring, for
  "awaiting your reply", how often a reply followed (precision) and how many such threads exist per week
  (volume against a weekly budget). *Gate:* a volume and precision the owner accepts, or stop.
- **E2: sender importance.** The per-sender reply learner with floors and "insufficient evidence";
  parity and held-out checks as in the covariate engine. *Gate:* held-out gain over "every sender equal".
- **E3: the card variant.** In the existing `email` slot; wording shown first; feedback wired; outcome
  labels recorded. *Gate:* owner review of real cards in shadow before they show.
- **E4: tier 2, only if approved.**

## Acceptance (for the whole item)

Retention, export and delete exist and are tested before any new field is read; a static test proves no
body or snippet is requested or stored; the card slot count is unchanged; every learned sender shows in
Teach-me and resets; nothing sends, drafts or changes a message.

## Decisions needed from the owner

1. Subject retention: 30, **90 (proposed)** or 365 days; and sender address after that: **hash (proposed)**
   or blank.
2. Fix the card path's `format=full` now, as its own small PR, ahead of the rest? (Recommended: yes.)
3. Whose mailbox is it, and may other residents connect theirs later? (Per-person stays in the design
   either way; not built.)
4. Try `gmail.metadata` on a throwaway account, accepting a re-authorise and a changed sync?
5. Allow the `To` / `Cc` headers (tier 1 gets sharper), or stay with `From` / `Subject` / `Date`?
6. Is the lake backed up anywhere? If so, delete must reach those copies too. The daily backup cron
   (`todo_db_backup_cron.md`) is a MySQL dump and I found no lake backup in the repo, but a volume snapshot
   outside the repo is possible, so this is unknown. `todo_signal_inventory.md` already says the lake
   should be treated as sensitive as the mailbox itself (backups, access).

## Out of scope

No body, snippet or attachment reading. No sending, drafting, labelling, archiving or deleting mail. No
other mailboxes. No cross-household learning. No new card. No cloud or third-party processing.
