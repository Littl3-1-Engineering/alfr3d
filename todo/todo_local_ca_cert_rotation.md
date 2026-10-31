# Local CA + self-healing HTTPS cert (cross-repo with alfr3d_deck)

**Problem:** the Deck pinned the NUC's self-signed *leaf* (`alfr3d_nuc.crt`, SAN = one LAN IP). Any
IP/network change broke TLS, and the pin was scoped to two hard-coded domains in
`network_security_config.xml`. Customers move networks, so this must be automatic.

**Design:** the Deck pins a long-lived local **CA**, not the leaf. The leaf is re-issued whenever
the host's addresses change; paired Decks never notice. Only a *CA* change (host rebuilt, CA key
lost) needs a human: the Deck blocks and asks the user to re-verify the fingerprint.

## Backend (this repo) -- written + DEPLOYED to the NUC 2026-10-26
- [x] `services/service_tls/` sidecar (`local_tls.py` + `app.py`): `ensure_ca` (never regenerates),
      `issue_leaf`, `leaf_needs_reissue` (missing / bad signature / <30d left / SAN drift),
      `host_sans` (LAN IPv4s, hostname(.local), `alfr3d.local`, localhost, `TLS_EXTRA_SANS`).
      HUPs nginx after a re-issue. CA key lives only in the `tls_ca` volume. Was a 60s loop;
      since 2026-10-28 a run-once container (`TLS_ONESHOT=1`), see
      [todo_on_demand_containers.md](todo_on_demand_containers.md): runs at every `compose up`
      (nginx waits with `service_completed_successfully`) and daily via `setup/tls_reissue.sh`.
- [x] `GET /api/tls/ca` (pem + sha256 + subject + not_after) and `GET /api/tls/ca.crt` in
      `service_api/routes/tls.py`; unauthenticated by design (public cert).
- [x] `docker-compose.yml`: `service-tls` (host network), nginx waits on it; `nginx.conf` /
      `nginx.conf.example` gain a `:443` server sharing `nginx-server-common.conf` with `:80`.
- [x] `tests/test_local_tls.py` (7 tests). Found+fixed: issuer-name compare can't tell a
      regenerated CA from the old one (same subject) -- must verify the signature.
- [ ] **Deploy to NUC.** `nginx.conf` is gitignored and the NUC's copy had drifted (the repo version
      had no :443 block at all), so merge the :443 server + `include` by hand there. Then
      `docker compose build service-tls && docker compose up -d service-tls nginx` (v2 only, see
      the v1/v2 trap). Compare `/api/tls/ca` sha256 against `service-tls` logs.
- [ ] Show the CA fingerprint in the web Nexus (Settings) so the user can compare it with the Deck.
- [x] README/AGENTS mention of `service_tls` + `/api/tls/*` (README added 2026-10-28; AGENTS already had it).

## Deck (alfr3d_deck) -- written 2026-10-26, verified on device (ASUS_AI2202, debug build)
- [x] `PinnedCaTrust` (`alfr3d/Alfr3dTls.kt`): chain validated against the pinned CA only,
      hostname check relaxed (identity = CA signature), installed per connection via
      `HttpAlfr3dClient.openTrusted` on all 5 request paths incl. SSE and token refresh.
- [x] Pairing: TLS failure on https -> `GET /api/tls/ca` (untrusted fetch, display-only; must be a
      self-signed CA, fingerprint computed locally) -> `CaOffer` -> `SecureLinkPanel` in both
      Settings layouts (TRUST / NOT NOW, UNPAIR). CA stored in `Alfr3dAuthStore`, kept across sign-out.
- [x] CA-changed state: same offer with `changed=true`, shown as "ALFR3D IDENTITY CHANGED"; never
      auto-accepted.
- [x] Removed `res/raw/alfr3d_nuc.crt` and the per-domain block in `network_security_config.xml`.
      One-time re-pair for existing installs (no legacy fallback, as decided).
- [x] `PinnedCaTrustTest` (7): real TLS handshakes against backend-issued fixtures.
- [x] On-device: `https://10.0.0.100` -> "SECURE LINK AVAILABLE" with the matching fingerprint ->
      TRUST -> CONNECTED. Forced a leaf rotation on the NUC (extra SAN, new serial): Deck stayed
      connected, no re-pair. Tailscale hostname (public cert) still works while a CA is pinned.
- [ ] Not exercised on device: the CA-changed ("IDENTITY CHANGED") warning and UNPAIR.
- [ ] Onboarding copy still says "enter a bare IP"; mention https/pairing there.
- [ ] Offer detection runs from the 5s connection probe only; a background-worker-only session
      won't surface an offer until the app is opened (acceptable, noted).

## Found while deploying
- Pinned mode first dropped system CAs, which would have broken the Tailscale hostname; fixed so a
  chain is accepted via the pinned CA *or* system CAs, with hostname checking skipped only for
  leaves the pinned CA signed (so a public cert for another domain is never accepted).

## Open
- Trust-on-first-use at pairing is the one unauthenticated moment; the fingerprint confirmation
  (and a QR from the web UI, later) is what closes it.
