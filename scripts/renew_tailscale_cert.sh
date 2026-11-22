#!/usr/bin/env bash
# Renew the Tailscale HTTPS cert (Let's Encrypt, 90 days) that nginx serves for the tailnet name,
# then reload nginx. `tailscale cert` re-issues only when the cert is close to expiry, so running
# this often is cheap. Installed by scripts/systemd/alfr3d-ts-cert.{service,timer}.
#
#   TS_HOSTNAME   tailnet FQDN (default: this node's, from `tailscale status --json`)
#   CERT_FILE     where nginx reads the cert   (default: <repo>/certs/ts.crt)
#   KEY_FILE      where nginx reads the key    (default: <repo>/certs/ts.key)
#
# Point CERT_FILE/KEY_FILE at the paths the Tailscale `:443` server block in the NUC's nginx
# config already uses. Always `docker compose` v2 (never docker-compose v1).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CERT_FILE="${CERT_FILE:-$REPO/certs/ts.crt}"
KEY_FILE="${KEY_FILE:-$REPO/certs/ts.key}"
TS_HOSTNAME="${TS_HOSTNAME:-$(tailscale status --json | python3 -c 'import sys,json; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')}"

before="$(sha256sum "$CERT_FILE" 2>/dev/null || true)"
tailscale cert --cert-file "$CERT_FILE" --key-file "$KEY_FILE" "$TS_HOSTNAME"
chmod 644 "$CERT_FILE"
chmod 640 "$KEY_FILE"
after="$(sha256sum "$CERT_FILE")"

if [ "$before" != "$after" ]; then
  echo "renewed $TS_HOSTNAME; reloading nginx"
  (cd "$REPO" && docker compose exec -T nginx nginx -s reload)
else
  echo "$TS_HOSTNAME cert unchanged"
fi
